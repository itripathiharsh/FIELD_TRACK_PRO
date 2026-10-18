import { describe, it, expect } from 'vitest';
import { generatePDFContent, verifyPDFContent } from '../utils/pdf-report';

describe('PDF Report Generation', () => {
    const sampleHeaders = ['Employee', 'Total', 'Completed'];
    const sampleRows = [
        ['John Smith', '10', '8'],
        ['Jane Doe', '15', '12'],
    ];

    it('generates a valid PDF with correct header', () => {
        const pdf = generatePDFContent({
            title: 'Employee Visit Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const header = String.fromCharCode(...pdf.slice(0, 8));
        expect(header).toBe('%PDF-1.4');
    });

    it('contains the report title', () => {
        const pdf = generatePDFContent({
            title: 'Employee Visit Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const result = verifyPDFContent(pdf, ['Employee Visit Report']);
        expect(result.valid).toBe(true);
        expect(result.errors).toEqual([]);
    });

    it('contains table headers', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const result = verifyPDFContent(pdf, ['Employee', 'Total', 'Completed']);
        expect(result.valid).toBe(true);
    });

    it('contains row data', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const result = verifyPDFContent(pdf, ['John Smith', 'Jane Doe', '10', '15']);
        expect(result.valid).toBe(true);
    });

    it('includes date range when provided', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
            dateRange: { startDate: '2026-01-01', endDate: '2026-01-31' },
        });

        const result = verifyPDFContent(pdf, ['Period: 2026-01-01 to 2026-01-31']);
        expect(result.valid).toBe(true);
    });

    it('includes generated timestamp', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const pdfString = new TextDecoder('latin1').decode(pdf);
        expect(pdfString).toContain('Generated:');
    });

    it('has valid PDF structure', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const result = verifyPDFContent(pdf, []);
        expect(result.valid).toBe(true);
        expect(result.errors).toEqual([]);
    });

    it('ends with EOF marker', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const eof = String.fromCharCode(...pdf.slice(-10));
        expect(eof).toContain('%%EOF');
    });

    it('has xref table with correct offsets', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        const pdfString = new TextDecoder('latin1').decode(pdf);

        // Verify xref exists
        expect(pdfString).toContain('xref');
        expect(pdfString).toContain('trailer');
        expect(pdfString).toContain('startxref');

        // Verify all objects are present
        expect(pdfString).toContain('/Type /Catalog');
        expect(pdfString).toContain('/Type /Pages');
        expect(pdfString).toContain('/Type /Page');
        expect(pdfString).toContain('/Type /Font');
    });

    it('handles many rows with multi-page support', () => {
        const manyRows = Array.from({ length: 50 }, (_, i) => [`Employee ${i}`, `${i * 5}`, `${i * 4}`]);

        const pdf = generatePDFContent({
            title: 'Large Report',
            headers: sampleHeaders,
            rows: manyRows,
        });

        const result = verifyPDFContent(pdf, ['Large Report', 'Employee 0', 'Employee 49']);
        expect(result.valid).toBe(true);

        // Should have multiple pages
        const pdfString = new TextDecoder('latin1').decode(pdf);
        const pageCount = (pdfString.match(/\/Type \/Page/g) || []).length;
        expect(pageCount).toBeGreaterThan(1);
    });

    it('handles special characters in data', () => {
        const pdf = generatePDFContent({
            title: 'Report (Q1 & Q2)',
            headers: ['Name', 'Notes'],
            rows: [['O\'Brien', 'Test (with) parens & ampersand']],
        });

        const result = verifyPDFContent(pdf, ['O\'Brien']);
        expect(result.valid).toBe(true);
    });

    it('produces non-trivial output', () => {
        const pdf = generatePDFContent({
            title: 'Test Report',
            headers: sampleHeaders,
            rows: sampleRows,
        });

        // PDF should be more than just a header - it should have substantial content
        expect(pdf.length).toBeGreaterThan(500);
    });

    it('xref table is byte-exact: every entry points at its own "<N> 0 obj" marker', () => {
        const pdf = generatePDFContent({
            title: 'Xref Test',
            headers: sampleHeaders,
            rows: sampleRows,
        });
        const s = new TextDecoder('latin1').decode(pdf);
        const buf = pdf;

        const sx = s.lastIndexOf('startxref');
        const xrefStart = parseInt(s.slice(sx + 'startxref'.length).trim().split(/\s/)[0], 10);
        const xrefSeg = s.slice(xrefStart, xrefStart + 1000);

        // Header must declare N entries and the table must contain exactly N lines.
        const m = xrefSeg.match(/^xref\s+0 (\d+)\s*\n/);
        expect(m).not.toBeNull();
        const count = parseInt(m![1], 10);
        const entryLines = xrefSeg
            .slice(m![0].length)
            .split('\n')
            .filter(l => /^\d{10} \d{5} [nf]/.test(l));
        expect(entryLines.length).toBe(count);

        // Entry 0 is the free head; each following line must point at its object.
        for (let k = 1; k < count; k++) {
            const off = parseInt(entryLines[k].slice(0, 10), 10);
            const marker = new TextDecoder('latin1').decode(buf.slice(off, off + 12));
            expect(marker.startsWith(`${k} 0 obj`)).toBe(true);
        }
    });

    it('xref table is byte-exact for multi-page output', () => {
        const manyRows = Array.from({ length: 50 }, (_, i) => [`Employee ${i}`, `${i * 5}`, `${i * 4}`]);
        const pdf = generatePDFContent({
            title: 'Large Report',
            headers: sampleHeaders,
            rows: manyRows,
        });
        const s = new TextDecoder('latin1').decode(pdf);
        const buf = pdf;

        const sx = s.lastIndexOf('startxref');
        const xrefStart = parseInt(s.slice(sx + 'startxref'.length).trim().split(/\s/)[0], 10);
        const xrefSeg = s.slice(xrefStart, xrefStart + 2000);

        const m = xrefSeg.match(/^xref\s+0 (\d+)\s*\n/);
        expect(m).not.toBeNull();
        const count = parseInt(m![1], 10);
        const entryLines = xrefSeg
            .slice(m![0].length)
            .split('\n')
            .filter(l => /^\d{10} \d{5} [nf]/.test(l));
        expect(entryLines.length).toBe(count);

        for (let k = 1; k < count; k++) {
            const off = parseInt(entryLines[k].slice(0, 10), 10);
            const marker = new TextDecoder('latin1').decode(buf.slice(off, off + 12));
            expect(marker.startsWith(`${k} 0 obj`)).toBe(true);
        }
    });
});


describe('PDF Report Generation (fallback) - validity fixes', () => {
    const decode = (pdf: Uint8Array) => new TextDecoder('latin1').decode(pdf);

    it('stream /Length and xref offsets are byte counts even with non-ASCII text (rupee, accents, CJK)', () => {
        const pdf = generatePDFContent({
            title: 'Rupee é Report 日本',
            headers: ['Name', 'Amount'],
            rows: [['Zoë Ünal', '₹1,23,456.00'], ['日本語', '₹9']],
        });
        const s = decode(pdf);
        // every "N 0 obj" is found exactly at its xref offset
        const xrefStart = parseInt(s.slice(s.lastIndexOf('startxref') + 9).trim().split(/\s/)[0], 10);
        const xref = s.slice(xrefStart);
        const m = xref.match(/^xref\s+0 (\d+)\s*\n/)!;
        const entries = xref.slice(m[0].length).split('\n').filter((l) => /^\d{10} \d{5} [nf]/.test(l));
        for (let k = 1; k < entries.length; k++) {
            const off = parseInt(entries[k].slice(0, 10), 10);
            expect(decode(pdf.slice(off, off + 12)).startsWith(`${k} 0 obj`)).toBe(true);
        }
        // declared stream length == actual bytes between "stream\n" and "\nendstream"
        const re = /<< \/Length (\d+) >>\nstream\n/g;
        let match: RegExpExecArray | null;
        let streams = 0;
        while ((match = re.exec(s))) {
            const start = match.index + match[0].length;
            const end = s.indexOf('\nendstream', start);
            expect(end - start).toBe(parseInt(match[1], 10));
            streams++;
        }
        expect(streams).toBeGreaterThan(0);
        // output is pure single-byte: no UTF-8 multi-byte sequences were written
        expect(pdf.length).toBe(s.length);
    });

    it('prints the rupee sign as "Rs." instead of garbage', () => {
        const s = decode(generatePDFContent({ title: 'T', headers: ['A'], rows: [['₹500']] }));
        expect(s).toContain('(Rs.500)');
        expect(s).not.toContain('â\u0082¹'); // no mojibake of the UTF-8 rupee bytes
    });

    it('is landscape A4 and wraps long cells instead of running off the page', () => {
        const long = 'Sri Venkateshwara Traders and Electronics Mega Store with a very long name '.repeat(4).trim();
        const pdf = generatePDFContent({
            title: 'Wide',
            headers: ['Brand', 'Outlet', 'Zone', 'Area', 'FOS', 'OS', 'B1', 'B2', 'B3', 'B4'],
            rows: [['USHA', long, 'Z', 'A', 'F', '1', '2', '3', '4', '5']],
        });
        const s = decode(pdf);
        expect(s).toContain('/MediaBox [0 0 842 595]');
        // the long cell is split over several Tj lines
        const tj = s.match(/\([^)]*(Sri|Venkateshwara|Store|Traders)[^)]*\) Tj/g) ?? [];
        expect(tj.length).toBeGreaterThan(1);
        // no text origin beyond the page width
        const xs = [...s.matchAll(/([\d.]+) [\d.]+ Td/g)].map((x) => parseFloat(x[1]));
        expect(Math.max(...xs)).toBeLessThan(842);
    });

    it('repeats the header row on every page and numbers the pages', () => {
        const rows = Array.from({ length: 120 }, (_, i) => [`Employee ${i}`, String(i), String(i)]);
        const s = decode(generatePDFContent({ title: 'Long', headers: ['Employee', 'Total', 'Completed'], rows }));
        const pages = (s.match(/\/Type \/Page /g) || []).length;
        expect(pages).toBeGreaterThan(2);
        expect((s.match(/\(Employee\) Tj/g) || []).length).toBe(pages);
        expect(s).toContain(`(Page 1 of ${pages}) Tj`);
        expect(s).toContain(`(Page ${pages} of ${pages}) Tj`);
    });

    it('renders an empty table with a "no rows" message (valid file)', () => {
        const pdf = generatePDFContent({ title: 'Empty', headers: ['A', 'B'], rows: [] });
        expect(verifyPDFContent(pdf, ['No rows match the selected filters.']).valid).toBe(true);
    });
});
