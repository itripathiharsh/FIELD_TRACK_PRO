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
