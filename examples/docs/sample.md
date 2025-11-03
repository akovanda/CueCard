# Pagination and Rate Limits

When listing orders, always specify a `limit` (default 25, max 100) and use the `cursor` from the previous response to get the next page.

If you receive HTTP 429, back off and retry with exponential delay. Include the `org_id` in all list calls; requests missing tenant context will 403.
