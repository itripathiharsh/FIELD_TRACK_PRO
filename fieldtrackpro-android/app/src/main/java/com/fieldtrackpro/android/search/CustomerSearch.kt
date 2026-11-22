package com.fieldtrackpro.android.search

import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.Locale

/**
 * Relevance ranking shared by every customer picker (Monthly Plan, Off-Beat Visit).
 *
 * The backend returns matches sorted ALPHABETICALLY and capped at 50, so for a short query like "s" the first page
 * was mostly names starting with "A" whose address contained an "s". Ranking is now done here, case-insensitively:
 *
 *   1 exact name  2 name starts with  3 name contains (any word order)  4 exact code  5 code partial
 *   6 address / area / territory  7 other server-side match (e.g. a linked Tally ledger name)
 *
 * Ties: a word in the name starting with the query first, then name A-Z, then code.
 */
object CustomerSearchRanker {

    enum class Tier { NAME_EXACT, NAME_PREFIX, NAME_CONTAINS, CODE_EXACT, CODE_PARTIAL, LOCATION, OTHER }

    data class Ranked(val customer: CustomerDto, val tier: Tier, val inScope: Boolean)

    fun normalize(value: String?): String =
        (value ?: "").lowercase(Locale.ROOT).trim().replace(Regex("\\s+"), " ")

    fun tier(customer: CustomerDto, query: String): Tier? {
        val q = normalize(query)
        if (q.isEmpty()) return null
        val tokens = q.split(' ')
        val name = normalize(customer.name)
        val codes = listOfNotNull(customer.outletCode, customer.dmsCode).map { normalize(it) }.filter { it.isNotEmpty() }
        val location = normalize(listOfNotNull(customer.address, customer.areaName, customer.territoryName).joinToString(" "))
        val everything = "$name ${codes.joinToString(" ")} $location"
        return when {
            name == q -> Tier.NAME_EXACT
            name.startsWith(q) -> Tier.NAME_PREFIX
            name.contains(q) || (tokens.size > 1 && tokens.all { name.contains(it) }) -> Tier.NAME_CONTAINS
            codes.any { it == q } -> Tier.CODE_EXACT
            codes.any { it.contains(q) } -> Tier.CODE_PARTIAL
            location.contains(q) || (tokens.size > 1 && tokens.all { everything.contains(it) }) -> Tier.LOCATION
            else -> null
        }
    }

    private fun wordPrefix(name: String, q: String): Boolean = name.split(' ').any { it.startsWith(q) }

    /**
     * Ranks [candidates]. Local candidates that do not match are dropped; server results that matched on a field we
     * cannot see (contact, Tally ledger) are kept as [Tier.OTHER] because the server is the authority for access.
     */
    fun rank(candidates: List<Pair<CustomerDto, Boolean>>, query: String, keepUnmatched: (CustomerDto) -> Boolean = { false }): List<Ranked> {
        val q = normalize(query)
        val byId = LinkedHashMap<String, Ranked>()
        for ((c, inScope) in candidates) {
            val t = tier(c, q) ?: if (keepUnmatched(c)) Tier.OTHER else null
            if (t == null) continue
            val existing = byId[c.id]
            // Same outlet from the portfolio and the directory: keep the in-scope copy (it is not redacted).
            if (existing == null || (!existing.inScope && inScope)) byId[c.id] = Ranked(c, t, inScope)
        }
        return byId.values.sortedWith(
            compareBy<Ranked> { it.tier.ordinal }
                .thenBy { if (wordPrefix(normalize(it.customer.name), q)) 0 else 1 }
                .thenBy { normalize(it.customer.name) }
                .thenBy { normalize(it.customer.outletCode ?: it.customer.dmsCode) }
                .thenBy { it.customer.id }
        )
    }
}

/** The employee's authorized outlets (backend scope), loaded once per signed-in user and kept for 10 minutes. */
object CustomerPortfolioCache {
    private const val TTL_MS = 10 * 60 * 1000L
    private val mutex = Mutex()
    private var userId: String? = null
    private var loadedAt = 0L
    private var customers: List<CustomerDto>? = null

    suspend fun get(
        currentUserId: String?,
        now: Long = System.currentTimeMillis(),
        force: Boolean = false,
        load: suspend () -> Resource<List<CustomerDto>>
    ): Resource<List<CustomerDto>> = mutex.withLock {
        val cached = customers
        if (!force && cached != null && userId == currentUserId && now - loadedAt < TTL_MS) return Resource.Success(cached)
        when (val res = load()) {
            is Resource.Success -> {
                customers = res.data
                userId = currentUserId
                loadedAt = now
                res
            }
            else -> res
        }
    }

    fun clear() {
        customers = null
        userId = null
        loadedAt = 0
    }
}

data class CustomerSearchState(
    val query: String = "",
    val results: List<CustomerSearchRanker.Ranked> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
    /** e.g. "Showing 50 of 312 matches. Type more to narrow down." or the 3-letter hint. */
    val hint: String? = null,
    val portfolioError: String? = null
)

/**
 * One search box's logic: local ranked search over the authorized portfolio (instant, complete - not just a loaded
 * page), plus a debounced directory search for queries of [minRemoteLength]+ characters (the backend only searches
 * the whole directory from 3 characters). A generation counter guarantees that a slow, older response can never
 * overwrite the results of a newer query.
 */
class CustomerSearchController(
    private val scope: CoroutineScope,
    private val currentUserId: () -> String?,
    private val loadPortfolio: suspend () -> Resource<List<CustomerDto>>,
    private val searchDirectory: suspend (String) -> Resource<Pair<List<CustomerDto>, Int>>,
    private val debounceMs: Long = 300,
    private val minRemoteLength: Int = 3,
    private val maxResults: Int = 50
) {
    private val _state = MutableStateFlow(CustomerSearchState())
    val state: StateFlow<CustomerSearchState> = _state.asStateFlow()

    private var portfolio: List<CustomerDto> = emptyList()
    private var portfolioJob: Job? = null
    private var searchJob: Job? = null
    private var generation = 0L

    /** Loads the portfolio (cached) and shows it for an empty query. */
    fun start(force: Boolean = false) {
        if (portfolioJob?.isActive == true) return
        portfolioJob = scope.launch {
            _state.value = _state.value.copy(isLoading = _state.value.results.isEmpty())
            when (val res = CustomerPortfolioCache.get(currentUserId(), force = force, load = loadPortfolio)) {
                is Resource.Success -> {
                    portfolio = res.data
                    _state.value = _state.value.copy(portfolioError = null)
                }
                is Resource.Error -> _state.value = _state.value.copy(portfolioError = res.message)
                else -> Unit
            }
            refreshLocal(_state.value.query, keepLoading = searchJob?.isActive == true)
        }
    }

    fun onQueryChange(raw: String) {
        val query = raw.take(80)
        val gen = ++generation
        searchJob?.cancel()
        refreshLocal(query, keepLoading = false)
        val q = CustomerSearchRanker.normalize(query)
        if (q.length < minRemoteLength) return
        _state.value = _state.value.copy(isLoading = true, error = null)
        searchJob = scope.launch {
            delay(debounceMs)
            val res = try {
                searchDirectory(q)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Resource.Error("Network error: ${e.javaClass.simpleName}")
            }
            if (gen != generation) return@launch // a newer query owns the results
            when (res) {
                is Resource.Success -> {
                    val (rows, total) = res.data
                    val local = portfolio.map { it to true }
                    val portfolioIds = portfolio.map { it.id }.toSet()
                    val remote = rows.map { it to (it.id in portfolioIds) }
                    val serverIds = rows.map { it.id }.toSet()
                    val ranked = CustomerSearchRanker.rank(local + remote, q) { it.id in serverIds }
                    _state.value = _state.value.copy(
                        results = ranked.take(maxResults),
                        isLoading = false,
                        error = null,
                        hint = if (total > rows.size) "Showing the best matches of $total. Type more of the name to narrow down." else null
                    )
                }
                is Resource.Error -> _state.value = _state.value.copy(isLoading = false, error = res.message)
                else -> _state.value = _state.value.copy(isLoading = false)
            }
        }
    }

    fun clear() = onQueryChange("")

    private fun refreshLocal(query: String, keepLoading: Boolean) {
        val q = CustomerSearchRanker.normalize(query)
        val results = if (q.isEmpty()) {
            portfolio.sortedBy { CustomerSearchRanker.normalize(it.name) }.take(maxResults)
                .map { CustomerSearchRanker.Ranked(it, CustomerSearchRanker.Tier.OTHER, true) }
        } else {
            CustomerSearchRanker.rank(portfolio.map { it to true }, q).take(maxResults)
        }
        _state.value = _state.value.copy(
            query = query,
            results = results,
            isLoading = keepLoading,
            error = null,
            hint = when {
                q.isEmpty() -> null
                q.length < minRemoteLength -> "Showing your outlets. Type $minRemoteLength or more letters to search all outlets."
                else -> null
            }
        )
    }
}
