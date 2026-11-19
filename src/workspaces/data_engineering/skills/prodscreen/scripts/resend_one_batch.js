// Paste into the documented cua_repl JavaScript session with resendTab bound
// to the authenticated Chrome tab. This is not a standalone script.
//
// Before running, retain explicit authorization for this exact batch and
// verify the current page's exact environment hostname, selected full client
// UUID, and complete input against the deduplicated recoverable IDs (maximum
// 1,000). CA client-wide resends require separate client and date authorization.
// Ensure at least 10 seconds have elapsed since any prior resend submission,
// across all clients and environments. Do not run for a confirmed batch.
//
// Afterward, inspect the fresh snapshot and capture a screenshot. Record a
// result attributable to this batch; a stale success label is not confirmation.
// On error, timeout, or ambiguity, stop and reconcile before any resubmission.
// Do not retry tasks or submit another batch until this batch is confirmed.
await resendTab.playwright.getByRole("button", { name: "Resend", exact: true }).click();
await resendTab.playwright.waitForTimeout(10_000);
nodeRepl.write(await resendTab.playwright.domSnapshot());
