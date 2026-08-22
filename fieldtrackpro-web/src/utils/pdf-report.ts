/**
 * PDF report generation utility.
 *
 * Generates valid PDF 1.4 documents from tabular report data.
 * Supports multi-page output with automatic page breaks.
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

export function generatePDFContent(options: PDFExportOptions): Uint8Array {
    const { title, headers, rows, dateRange, filters, summaryKPIs } = options;

    const escapePDF = (str: string) =>
        str.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');

    const LINE_HEIGHT = 14;
    const MARGIN_TOP = 60;
    const MARGIN_BOTTOM = 40;
    const PAGE_HEIGHT = 842;
    const PAGE_WIDTH = 595;

    interface PageBlock {
        lines: string[];
    }

    const blocks: PageBlock[] = [];
    let current: PageBlock = { lines: [] };
    let y = PAGE_HEIGHT - MARGIN_TOP;

    const pushText = (text: string, fontSize: number) => {
        if (y < MARGIN_BOTTOM) {
            blocks.push(current);
            current = { lines: [] };
            y = PAGE_HEIGHT - MARGIN_TOP;
        }
        current.lines.push('BT');
        current.lines.push(`/F1 ${fontSize} Tf`);
        current.lines.push(`50 ${Math.round(y)} Td`);
        current.lines.push(`(${escapePDF(text)}) Tj`);
        current.lines.push('ET');
        y -= LINE_HEIGHT * (fontSize / 10);
    };

    // Title
    pushText(`FieldTrack - ${title}`, 15);
    y -= 4;

    // Generated timestamp
    pushText(`Generated: ${new Date().toLocaleString()}`, 8);
    y -= 2;

    // Date range / Filters
    if (dateRange?.startDate || dateRange?.endDate) {
        pushText(`Period: ${dateRange.startDate || 'Start'} to ${dateRange.endDate || 'End'}`, 9);
        y -= 2;
    }
    if (filters) {
        const filterStr = Object.entries(filters)
            .filter(([, v]) => !!v && v !== 'ALL')
            .map(([k, v]) => `${k}: ${v}`)
            .join(' | ');
        if (filterStr) {
            pushText(`Filters Applied: ${filterStr}`, 8);
            y -= 2;
        }
    }

    // Summary KPIs
    if (summaryKPIs && summaryKPIs.length > 0) {
        const kpiStr = summaryKPIs.map((k) => `${k.label}: ${k.value}`).join('   |   ');
        pushText(`Summary: ${kpiStr}`, 9);
        y -= 4;
    }

    pushText('='.repeat(Math.min(95, Math.max(40, headers.length * 14))), 8);
    y -= 4;

    // Table header
    pushText(headers.join('  |  '), 8);
    y -= 2;

    pushText('-'.repeat(Math.min(95, Math.max(40, headers.length * 14))), 8);
    y -= 4;

    // Table rows
    for (const row of rows) {
        pushText(row.join('  |  '), 8);
    }

    blocks.push(current);

    // Build content streams per page
    const pageContentStreams: string[] = [];
    for (const block of blocks) {
        pageContentStreams.push(['q', ...block.lines, 'Q'].join('\n'));
    }

    // Build PDF with byte-exact xref offsets
    // Object numbering:
    //   1 = Catalog
    //   2 = Pages
    //   3..(3+numPages-1) = Page objects
    //   (3+numPages)..(3+2*numPages-1) = Content stream objects
    //   last = Font object
    const parts: string[] = [];
    const offsets: number[] = [];

    const addPart = (text: string) => {
        offsets.push(parts.join('').length);
        parts.push(text);
    };

    const numPages = pageContentStreams.length;
    const pageObjStart = 3;
    const contentObjStart = pageObjStart + numPages;
    const fontObjNum = contentObjStart + numPages;

    addPart('%PDF-1.4\n');
    addPart('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n');
    addPart(`2 0 obj\n<< /Type /Pages /Kids [${pageContentStreams.map((_, i) => `${pageObjStart + i} 0 R`).join(' ')}] /Count ${numPages} >>\nendobj\n`);

    for (let i = 0; i < numPages; i++) {
        const pageNum = pageObjStart + i;
        const contentNum = contentObjStart + i;
        addPart(`${pageNum} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] /Contents ${contentNum} 0 R /Resources << /Font << /F1 ${fontObjNum} 0 R >> >> >>\nendobj\n`);
    }

    addPart(`${fontObjNum} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n`);

    for (let i = 0; i < numPages; i++) {
        const contentNum = contentObjStart + i;
        const stream = pageContentStreams[i];
        addPart(`${contentNum} 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`);
    }

    const xrefStart = parts.join('').length;
    const totalObjs = fontObjNum + 1;

    // Map every PDF object number to the byte offset where it was written.
    // `offsets` is ordered by addPart() calls: [header, catalog(1), pages(2),
    // page objects(3..), font(fontObjNum), content objects]. The header is not
    // an object, so it is excluded from the xref table.
    const objectOffsets = new Map<number, number>();
    objectOffsets.set(1, offsets[1]);
    objectOffsets.set(2, offsets[2]);
    for (let i = 0; i < numPages; i++) {
        objectOffsets.set(pageObjStart + i, offsets[3 + i]);
    }
    objectOffsets.set(fontObjNum, offsets[3 + numPages]);
    for (let i = 0; i < numPages; i++) {
        objectOffsets.set(contentObjStart + i, offsets[4 + numPages + i]);
    }

    let xref = `xref\n0 ${totalObjs}\n0000000000 65535 f \n`;
    for (let n = 1; n < totalObjs; n++) {
        const off = objectOffsets.get(n) ?? 0;
        xref += `${String(off).padStart(10, '0')} 00000 n \n`;
    }

    const trailer = `trailer\n<< /Size ${totalObjs} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;

    const pdfString = parts.join('') + xref + trailer;
    return new TextEncoder().encode(pdfString);
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
