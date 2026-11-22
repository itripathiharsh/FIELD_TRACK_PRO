package com.fieldtrackpro.android.search

import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource

/**
 * Data sources for customer pickers, using only the existing GET /api/v1/customers contract:
 *  - portfolio: no `search` parameter -> the backend returns exactly the caller's authorized outlets
 *    (assigned, in covered areas / home territory, or on their planned visits); paged until complete.
 *  - directory: `search` of 3+ characters -> the backend also returns other outlets, redacted (off-beat picker).
 */
object CustomerSources {
    private const val PAGE = 1000
    private const val MAX_PORTFOLIO = 5000

    suspend fun loadPortfolio(repo: CustomerRepository): Resource<List<CustomerDto>> {
        val all = ArrayList<CustomerDto>()
        var skip = 0
        while (true) {
            when (val res = repo.getCustomers(skip = skip, limit = PAGE)) {
                is Resource.Success -> {
                    all += res.data.customers
                    skip += res.data.customers.size
                    if (res.data.customers.isEmpty() || !res.data.hasMore || all.size >= MAX_PORTFOLIO) return Resource.Success(all)
                }
                is Resource.Error -> return Resource.Error(res.message, res.code)
                else -> return Resource.Error("Could not load outlets")
            }
        }
    }

    suspend fun searchDirectory(repo: CustomerRepository, query: String): Resource<Pair<List<CustomerDto>, Int>> =
        when (val res = repo.getCustomers(skip = 0, limit = 50, search = query)) {
            is Resource.Success -> Resource.Success(res.data.customers to res.data.totalCount)
            is Resource.Error -> Resource.Error(res.message, res.code)
            else -> Resource.Error("Search failed")
        }
}
