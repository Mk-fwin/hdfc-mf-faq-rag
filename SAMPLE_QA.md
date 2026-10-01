# Sample Q&A - Mutual Fund FAQ assistant

Facts-only assistant over five HDFC Direct Growth scheme pages on Groww.
Answers generated in mode: {'groq:attempt1': 9}

Refusals carry one link and no 'Last updated' line, because no source was
consulted; source-derived answers carry both.

## 1. expense ratio

**Q:** What is the expense ratio of HDFC Large Cap Fund Direct Growth?

**Why this test:** expense_ratio chunk alone, scheme-scoped: the ratio only, no exit load or base ratio

**A:** The expense ratio of HDFC Large Cap Fund Direct Growth is 1.03%.
https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth (HDFC Large Cap Fund Direct Growth, expense_ratio)

## 2. exit load

**Q:** What is the exit load on HDFC Small Cap Fund Direct Growth?

**Why this test:** is_current=1 only; superseded versions must not appear

**A:** The exit load on HDFC Small Cap Fund Direct Growth is 1% if redeemed within one year.
https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth (HDFC Small Cap Fund Direct Growth, exit_load_current)

## 3. ELSS lock-in

**Q:** What is the lock-in period for HDFC ELSS Tax Saver Fund?

**Why this test:** the only lockin chunk in the corpus

**A:** The lock‑in period for HDFC ELSS Tax Saver Fund is 3 years.
https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth (HDFC ELSS Tax Saver Fund Direct Plan Growth, lockin)

## 4. minimum SIP

**Q:** What is the minimum SIP amount for HDFC Balanced Advantage Fund?

**Why this test:** minimums chunk

**A:** The minimum SIP amount for HDFC Balanced Advantage Fund Direct Growth is Rs 100.
https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth (HDFC Balanced Advantage Fund Direct Growth, minimums)

## 5. alias: HDFC Equity

**Q:** What is the benchmark of HDFC Equity Fund?

**Why this test:** alias -> hdfc-equity-fund-direct-growth (Flexi Cap)

**A:** The benchmark of the HDFC Equity Fund is the NIFTY 500 Total Return Index.
https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth (HDFC Flexi Cap Direct Plan Growth (formerly HDFC Equity Fund), objective_benchmark)

## 6. fund manager

**Q:** Who manages HDFC Small Cap Fund?

**Why this test:** fund_manager section boost

**A:** HDFC Small Cap Fund is managed by Dhruv Muchhal and Chirag Setalvad.
https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth (HDFC Small Cap Fund Direct Growth, fund_manager)

## 7. advice

**Q:** Should I buy HDFC Large Cap Fund?

**Why this test:** refuse advice, no retrieval

**A:** I can't give investment advice or recommend a scheme, and I don't know your goals, time horizon or risk tolerance. SEBI's mutual fund guide explains how to evaluate schemes against your own criteria. https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMutualFund=yes

## 8. comparison

**Q:** Which is better, HDFC Large Cap Fund or HDFC Small Cap Fund?

**Why this test:** refuse comparison, link the matched scheme page

**A:** I don't calculate returns, project future values, or compare schemes' performance. For performance figures, read the official monthly factsheet published by HDFC Mutual Fund and the scheme's past NAV history on its page. https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth

## 9. PII

**Q:** <redacted: 83 chars>

**Why this test:** reject PII without storing it

**A:** I can't accept personal details -- please remove any PAN, Aadhaar, account number, OTP, phone number or email address. I don't need them to answer a question about a mutual fund, and I never store what you send me. https://groww.in/help

## 10. statement download

**Q:** How do I download my account statement for HDFC ELSS?

**Why this test:** explicit not-covered reply with a verified link

**A:** I can't answer that from my sources: I only cover facts published on the five HDFC scheme pages in my corpus, and none of them explain how to download account statements. CAMS is the registrar and transfer agent that issues these statements, and Groww's help centre has the download steps. https://www.camsonline.com/

## 11. no scheme named

**Q:** What's the expense ratio?

**Why this test:** scheme-scoped fact with no scheme: must ask which, must not guess a fund

**A:** Which scheme do you mean? My corpus covers five HDFC Direct Growth schemes: HDFC Large Cap Fund Direct Growth, HDFC Flexi Cap Direct Plan Growth (formerly HDFC Equity Fund), HDFC ELSS Tax Saver Fund Direct Plan Growth, HDFC Small Cap Fund Direct Growth, HDFC Balanced Advantage Fund Direct Growth. Tell me the scheme name and I'll give you the figure with its source. https://groww.in/mutual-funds

## 12. advice as fact

**Q:** Is HDFC Small Cap safe?

**Why this test:** 'is X safe' is a suitability judgement: must refuse, not quote the risk label

**A:** I can't give investment advice or recommend a scheme, and I don't know your goals, time horizon or risk tolerance. SEBI's mutual fund guide explains how to evaluate schemes against your own criteria. https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMutualFund=yes

## 13. rank on non-return metric

**Q:** Which HDFC fund has the lowest expense ratio?

**Why this test:** cross-scheme ranking on fees: refuse like any other comparison

**A:** I don't calculate returns, project future values, or compare schemes' performance. For performance figures, read the official monthly factsheet published by HDFC Mutual Fund and the scheme's past NAV history on its page. https://groww.in/mutual-funds

## 14. out of scope fund

**Q:** Expense ratio of SBI Bluechip Fund

**Why this test:** a real fund outside the corpus: must not answer from a near-miss HDFC chunk

**A:** I don't have SBI in my sources: my corpus covers five HDFC Mutual Fund Direct Growth scheme pages on Groww and nothing else. For a fund outside that set, read its own official factsheet or its AMFI listing. https://amfiindia.com/

## 15. PII plus valid question

**Q:** <redacted: 44 chars>

**Why this test:** PII must win: refuse and redact, even though the question is otherwise answerable

**A:** I can't accept personal details -- please remove any PAN, Aadhaar, account number, OTP, phone number or email address. I don't need them to answer a question about a mutual fund, and I never store what you send me. https://groww.in/help

## 16. out of scope: unlisted AMC

**Q:** Expense ratio of Motilal Oswal Large Cap Fund

**Why this test:** an AMC that was never in any list: must be caught structurally, not by name

**A:** I don't have Motilal Oswal in my sources: my corpus covers five HDFC Mutual Fund Direct Growth scheme pages on Groww and nothing else. For a fund outside that set, read its own official factsheet or its AMFI listing. https://amfiindia.com/

## 17. out of scope: no 'Fund' suffix

**Q:** Exit load of Nippon India Small Cap

**Why this test:** a real foreign scheme whose name omits 'Fund': must refuse, not cite an HDFC page

**A:** I don't have Nippon in my sources: my corpus covers five HDFC Mutual Fund Direct Growth scheme pages on Groww and nothing else. For a fund outside that set, read its own official factsheet or its AMFI listing. https://amfiindia.com/

## 18. fund manager, 2 managers

**Q:** Who manages HDFC Small Cap Fund?

**Why this test:** must name every manager on the page, not just the top-ranked one

**A:** HDFC Small Cap Fund is managed by Dhruv Muchhal and Chirag Setalvad.
https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth (HDFC Small Cap Fund Direct Growth, fund_manager)

## 19. fund manager, 6 managers

**Q:** Who manages HDFC Balanced Advantage Fund?

**Why this test:** a six-manager roster must still fit the 3-sentence limit, month+year only

**A:** The HDFC Balanced Advantage Fund is managed by six fund managers: Anil Bamboli, Arun Agarwal, Dhruv Muchhal, Nandita Menezes, Gopal Agrawal, and Ihab Dalwai.
https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth (HDFC Balanced Advantage Fund Direct Growth, fund_manager)

## 20. clarification answered by name

**Q:** What's the expense ratio?

**A:** Which scheme do you mean? My corpus covers five HDFC Direct Growth schemes: HDFC Large Cap Fund Direct Growth, HDFC Flexi Cap Direct Plan Growth (formerly HDFC Equity Fund), HDFC ELSS Tax Saver Fund Direct Plan Growth, HDFC Small Cap Fund Direct Growth, HDFC Balanced Advantage Fund Direct Growth. Tell me the scheme name and I'll give you the figure with its source. https://groww.in/mutual-funds

**Q:** What's the expense ratio? HDFC Small Cap Fund   (user sent: HDFC Small Cap Fund)

**Why this test:** a bare scheme name must complete the held question, not start a new lookup; the same name sent again must then be asked what to look up, because the question was answered and not left in memory

**A:** The expense ratio of the HDFC Small Cap Fund is 0.78%.
https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth
Last updated from sources: 2026-09-29

**Sources used:**

- https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth (HDFC Small Cap Fund Direct Growth, expense_ratio)

**Q:** HDFC Small Cap Fund

**A:** What would you like to know about HDFC Small Cap Fund Direct Growth? (e.g. expense ratio, exit load, minimum SIP) https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth

## 21. scheme name, no question

**Q:** HDFC Equity

**Why this test:** a bare alias with no held question: ask what to look up, never return unrelated chunks; an alias must still name the Flexi Cap page

**A:** What would you like to know about HDFC Flexi Cap Direct Plan Growth (formerly HDFC Equity Fund)? (e.g. expense ratio, exit load, minimum SIP) https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth

