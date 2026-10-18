/**
 * Client-side PDF generation utility (FALLBACK ONLY).
 *
 * The Reports and Collections pages download real server-side PDFs
 * (reportlab; see backend app/services/report_exports.py). This helper remains
 * only for screens that have no server export (e.g. the executive dashboard).
 *
 * Generates valid PDF 1.4 documents from tabular data:
 *  - landscape A4, real table columns with wrapped cells and a repeating header row,
 *  - "Page x of y" footer,
 *  - byte-exact xref offsets and stream lengths (the document is pure Latin-1, so one
 *    character == one byte; characters outside Latin-1 are transliterated),
 *  - the rupee sign is printed as "Rs." because the built-in Helvetica has no glyph for it.
 */

export interface PDFExportOptions {
    title: string;
    headers: string[];
    rows: string[][];
    dateRange?: {
        startDate?: string;
        endDate?: string;
    };
    filters?: Record<string, string>;
    summaryKPIs?: Array<{ label: string; value: string }>;
}

const PAGE_WIDTH = 842; // A4 landscape
const PAGE_HEIGHT = 595;
const MARGIN_X = 28;
const MARGIN_TOP = 34;
const MARGIN_BOTTOM = 34;
const CELL_PAD = 3;

/** Make text safe for a WinAnsi/Latin-1 Helvetica string: rupee -> Rs., anything else outside Latin-1 -> '?'. */
export function toLatin1(text: string): string {
    return text
        .replace(/₹/g, 'Rs.')
        .replace(/[‐-―−]/g, '-')
        .replace(/[‘’]/g, "'")
        .replace(/[“”]/g, '"')
        .replace(/…/g, '...')
        .split('')
        .map((ch) => (ch.charCodeAt(0) > 0xff ? '?' : ch))
        .join('');
}

const escapePDF = (str: string) =>
    str.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)').replace(/\r|\n/g, ' ');

// Approximate Helvetica advance widths (per 1000 em) - good enough for wrapping decisions.
const NARROW = new Set('iljtfI.,:;|!\'"()[] '.split(''));
const WIDE = new Set('mwMW@%'.split(''));
const charWidth = (ch: string, size: number): number => {
    if (NARROW.has(ch)) return size * 0.28;
    if (WIDE.has(ch)) return size * 0.85;
    if (ch >= 'A' && ch <= 'Z') return size * 0.68;
    return size * 0.54;
};
const textWidth = (s: string, size: number) => {
    let w = 0;
    for (const ch of s) w += charWidth(ch, size);
    return w;
};

function wrap(text: string, maxWidth: number, size: number): string[] {
    const out: string[] = [];
    for (const para of text.split(/\n/)) {
        let line = '';
        for (const word of para.split(/\s+/).filter(Boolean)) {
            let w = word;
            // hard-break a word that cannot fit on a line of its own
            while (textWidth(w, size) > maxWidth && w.length > 1) {
                let cut = 1;
                while (cut < w.length && textWidth(w.slice(0, cut + 1), size) <= maxWidth) cut++;
                if (line) {
                    out.push(line);
                    line = '';
                }
                out.push(w.slice(0, cut));
                w = w.slice(cut);
            }
            const candidate = line ? `${line} ${w}` : w;
            if (textWidth(candidate, size) <= maxWidth) {
                line = candidate;
            } else {
                if (line) out.push(line);
                line = w;
            }
        }
        out.push(line);
    }
    return out.length ? out : [''];
}

export function generatePDFContent(options: PDFExportOptions): Uint8Array {
    const { title, headers, rows, dateRange, filters, summaryKPIs } = options;
    const clean = (s: unknown) => toLatin1(String(s ?? ''));

    const usable = PAGE_WIDTH - 2 * MARGIN_X;
    const ncols = Math.max(headers.length, 1);
    const fontSize = ncols <= 8 ? 8 : ncols <= 12 ? 7 : 6.2;
    const lineH = fontSize + 2.2;

    // ---- column widths: natural content width, then scale down to fit ------------------
    const cleanHeaders = headers.map(clean);
    const cleanRows = rows.map((r) => headers.map((_, i) => clean(r[i])));
    const natural = cleanHeaders.map((h, i) => {
        let longest = textWidth(h, fontSize);
        for (const r of cleanRows) longest = Math.max(longest, Math.min(textWidth(r[i], fontSize), 170));
        return longest + 2 * CELL_PAD + 2;
    });
    const total = natural.reduce((a, b) => a + b, 0);
    const colW = total > usable ? natural.map((w) => Math.max(34, (w / total) * usable)) : natural.map((w) => w + (usable - total) / ncols);
    const colX: number[] = [];
    colW.reduce((x, w, i) => {
        colX[i] = x;
        return x + w;
    }, MARGIN_X);

    // ---- pages -------------------------------------------------------------------------
    const pages: string[][] = [];
    let ops: string[] = [];
    let y = PAGE_HEIGHT - MARGIN_TOP;

    const text = (s: string, x: number, yy: number, size: number, bold = false, white = false) => {
        ops.push('BT', `/${bold ? 'F2' : 'F1'} ${size} Tf`, white ? '1 1 1 rg' : '0 0 0 rg', `${x.toFixed(1)} ${yy.toFixed(1)} Td`, `(${escapePDF(s)}) Tj`, 'ET');
    };
    const newPage = () => {
        pages.push(ops);
        ops = [];
        y = PAGE_HEIGHT - MARGIN_TOP;
    };

    const header = () => {
        const h = Math.max(...cleanHeaders.map((hd, i) => wrap(hd, colW[i] - 2 * CELL_PAD, fontSize).length)) * lineH + 4;
        ops.push('0.12 0.23 0.54 rg', `${MARGIN_X} ${(y - h).toFixed(1)} ${usable.toFixed(1)} ${h.toFixed(1)} re f`);
        cleanHeaders.forEach((hd, i) => {
            wrap(hd, colW[i] - 2 * CELL_PAD, fontSize).forEach((ln, k) => {
                text(ln, colX[i] + CELL_PAD, y - 2 - fontSize - k * lineH + 1, fontSize, true, true);
            });
        });
        y -= h;
    };

    const note = (s: string, size: number, bold = false) => {
        for (const ln of wrap(s, usable, size)) {
            text(ln, MARGIN_X, y - size, size, bold);
            y -= size + 3;
        }
    };

    note(`FieldTrack - ${clean(title)}`, 15, true);
    y -= 2;
    note(`Generated: ${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST`, 8);
    if (dateRange?.startDate || dateRange?.endDate) {
        note(`Period: ${dateRange.startDate || 'Start'} to ${dateRange.endDate || 'End'}`, 9);
    }
    if (filters) {
        const filterStr = Object.entries(filters)
            .filter(([, v]) => !!v && v !== 'ALL')
            .map(([k, v]) => `${k}: ${v}`)
            .join(' | ');
        if (filterStr) note(`Filters Applied: ${clean(filterStr)}`, 8);
    }
    if (summaryKPIs && summaryKPIs.length > 0) {
        note(`Summary: ${clean(summaryKPIs.map((k) => `${k.label}: ${k.value}`).join('   |   '))}`, 9, true);
    }
    y -= 6;
    header();

    cleanRows.forEach((r, ri) => {
        const cellLines = r.map((c, i) => wrap(c, colW[i] - 2 * CELL_PAD, fontSize));
        const h = Math.max(...cellLines.map((l) => l.length)) * lineH + 3;
        if (y - h < MARGIN_BOTTOM) {
            newPage();
            header();
        }
        if (ri % 2 === 1) {
            ops.push('0.95 0.96 0.97 rg', `${MARGIN_X} ${(y - h).toFixed(1)} ${usable.toFixed(1)} ${h.toFixed(1)} re f`);
        }
        cellLines.forEach((lines, i) => {
            lines.forEach((ln, k) => text(ln, colX[i] + CELL_PAD, y - 1.5 - fontSize - k * lineH + 1, fontSize));
        });
        ops.push('0.82 0.84 0.86 RG', '0.25 w', `${MARGIN_X} ${(y - h).toFixed(1)} m ${(MARGIN_X + usable).toFixed(1)} ${(y - h).toFixed(1)} l S`);
        y -= h;
    });
    if (rows.length === 0) {
        y -= 4;
        note('No rows match the selected filters.', 8);
    }
    pages.push(ops);

    // page footers
    const contents = pages.map((p, i) => {
        const footer: string[] = [];
        const label = `Page ${i + 1} of ${pages.length}`;
        footer.push('BT', '/F1 7 Tf', '0.4 0.4 0.4 rg', `${(PAGE_WIDTH - MARGIN_X - textWidth(label, 7)).toFixed(1)} 16 Td`, `(${label}) Tj`, 'ET');
        footer.push('BT', '/F1 7 Tf', '0.4 0.4 0.4 rg', `${MARGIN_X} 16 Td`, `(FieldTrack - ${escapePDF(clean(title))}) Tj`, 'ET');
        return ['q', ...p, ...footer, 'Q'].join('\n');
    });

    // ---- serialise: Latin-1, one char == one byte, so offsets/lengths are exact bytes ---------
    // Object numbering: 1 Catalog, 2 Pages, 3..(2+n) Page, (3+n)..(2+2n) Content, (3+2n) F1, (4+2n) F2
    const n = contents.length;
    const pageObj = (i: number) => 3 + i;
    const contentObj = (i: number) => 3 + n + i;
    const f1 = 3 + 2 * n;
    const f2 = f1 + 1;
    const objects: string[] = [];
    objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    objects[2] = `<< /Type /Pages /Kids [${contents.map((_, i) => `${pageObj(i)} 0 R`).join(' ')}] /Count ${n} >>`;
    for (let i = 0; i < n; i++) {
        objects[pageObj(i)] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] /Contents ${contentObj(i)} 0 R /Resources << /Font << /F1 ${f1} 0 R /F2 ${f2} 0 R >> >> >>`;
        objects[contentObj(i)] = `<< /Length ${contents[i].length} >>\nstream\n${contents[i]}\nendstream`;
    }
    objects[f1] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
    objects[f2] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';

    let body = '%PDF-1.4\n';
    const offsets: number[] = [];
    for (let k = 1; k < objects.length; k++) {
        offsets[k] = body.length;
        body += `${k} 0 obj\n${objects[k]}\nendobj\n`;
    }
    const xrefStart = body.length;
    const count = objects.length; // includes the free head entry 0
    let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
    for (let k = 1; k < count; k++) xref += `${String(offsets[k]).padStart(10, '0')} 00000 n \n`;
    const pdf = `${body}${xref}trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;

    const bytes = new Uint8Array(pdf.length);
    for (let i = 0; i < pdf.length; i++) bytes[i] = pdf.charCodeAt(i) & 0xff;
    return bytes;
}

/**
 * Verify that a PDF byte array contains expected text content.
 * Performs basic structural validation and text extraction.
 */
export function verifyPDFContent(pdfBytes: Uint8Array, expectedTexts: string[]): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    // Check PDF header
    const header = String.fromCharCode(...pdfBytes.slice(0, 8));
    if (!header.startsWith('%PDF-1.')) {
        errors.push(`Invalid PDF header: ${header}`);
    }

    // Check EOF marker
    const eof = String.fromCharCode(...pdfBytes.slice(-20));
    if (!eof.includes('%%EOF')) {
        errors.push('Missing %%EOF marker');
    }

    // Convert full bytes to string for text searching
    const pdfString = new TextDecoder('latin1').decode(pdfBytes);

    // Check for required PDF structure
    if (!pdfString.includes('xref')) {
        errors.push('Missing xref table');
    }
    if (!pdfString.includes('trailer')) {
        errors.push('Missing trailer');
    }
    if (!pdfString.includes('/Type /Catalog')) {
        errors.push('Missing Catalog object');
    }
    if (!pdfString.includes('/Type /Page')) {
        errors.push('Missing Page object');
    }
    if (!pdfString.includes('/Length')) {
        errors.push('Missing content stream length');
    }

    // Check expected text content
    for (const text of expectedTexts) {
        if (!pdfString.includes(text)) {
            errors.push(`Missing expected text: "${text}"`);
        }
    }

    return { valid: errors.length === 0, errors };
}
