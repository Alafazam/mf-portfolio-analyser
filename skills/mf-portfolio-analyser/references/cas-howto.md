# Getting the MF Central Detailed CAS

The analyser needs the **Detailed** Consolidated Account Statement (every purchase with date, units and NAV), not the Summary.

1. Go to **mfcentral.com** and sign in with your PAN and the OTP sent to your registered mobile/email.
2. Open **Reports → CAS** (sometimes "Statements").
3. Choose **Detailed**.
4. Set **From date** to the earliest date allowed (or "Since inception") and **To date** to today. A statement that starts later leaves older units without a known cost; those funds are then left out of tax planning.
5. Include all folios. Download the PDF (set a password if asked).

Then run, in your own terminal (so the password prompt stays hidden):

```bash
cd <plugin folder> && python3 -m mfpa run --cas ~/Downloads/<your-cas>.pdf
```

The PDF and its text stay on your computer. The tool deletes the extracted text after it has written a redacted summary (no name, PAN, address, contact details or folio numbers) to `~/.mfpa/runs/…`.

Supported in v1: MF Central "Detailed" CAS only. CAMS/KFintech emailed CAS and NSDL/CDSL demat CAS use different layouts and aren't supported yet.
