# GSC Monitoring Methodology

This methodology document is for an AI agent to understand how I monitor Google Search Console data for SEO monitoring.

## Objective

The objective of GSC monitoring is to detect meaningful performance changes, identify where those changes are concentrated, and narrow down likely areas requiring further investigation. Do not claim an underlying root cause unless the available evidence directly supports it.

During my analysis, I try to have following obectives in my mind: 

- site-wide: Is the website not performing well as a whole entity?
- page-specific: Are there any pages that are not performing well?
- query-specific: Are there any queries that are not performing well?
- cluster-specific: Are there any clusters (both query and page) that are not performing well?

Core objective is to identify meaningful performance changes, determine where they are concentrated, and narrow down potential causes for further investigation.

## Metrics

As for the metrics that matter for SEO monitoring, I use the following:

- clicks
- impressions
- CTR
- position

Above four are the core metrics that I use to monitor website performance.

## Investigation Process

I start my investigation by trying to find the answer for the first objective: which is to establish if the website is not performing well as a whole entity. To do that idea is very simple look at the metrics of a website over time (comparing website stats for last 28 days vs previous 28 days is a good starting point).

TESTING FORMULA:

Percentage change =
(Current Period - Previous Period) / Previous Period × 100

Example:
Previous impressions = 10,000
Current impressions = 8,000

(8,000 - 10,000) / 10,000 × 100 = -20%

Therefore impressions declined by 20%.

For decline detection:
- Percentage change <= -20% = meaningful decline
- Percentage change > -20% = does not meet the decline threshold

For growth:
- Percentage change >= +20% = meaningful growth

For example: if last 28 days impressions were 10000 and previous 28 days impressions were 15000, then I calculate the percentage drop: (10000 - 15000) / 15000 = -33.3%. My threshold for a drop is 20%, so I can conclude that there is a drop in impressions. 

However, during this investigation I also look at the other metrics - most notably clicks, I test the clicks using the same test. Compare the last 28 days clicks vs previous 28 days clicks to see if there is a drop. Same formula is used to calculate the percentage drop. If the percentage drop is above the threshold then I can conclude that there is a drop in clicks. Then same principle is applied to other metrics. If both clicks and impressions are below the threshold then I can conclude that there is no issue. 

If neither clicks nor impressions shows a meaningful site-wide decline, I report that no site-wide performance issue was detected. There is no need to automatically continue to page/query investigation unless the user's question specifically asks for deeper analysis or there is another signal requiring investigation.

Also clicks and impressions holds priority over other metrics. So if both clicks and impressions are above the threshold then I can conclude that there is an issue, regardless of other metrics.

Once site-wide issuse is identified, I move towards the next objective: which is to find out if the issue is specific to a particular page and if so then which page it is. I gather the page-level data. Idea is to treat each page as a separate entity and perform the same comparison rules as site-wide data. So, effectively, I am comparing each page with its last 28 days data vs previous 28 days data. Then using the same test we performed on site-wide data, I compare the page-level data to see if there is a drop. Pages that show a drop are considered to be the ones with the issue. During this process we also calculate the page importance to website. For example: if a PAGE A was bringing 20% of website traffic over last 3 months then that page is marked as Grade A. If a PAGE B was bringing 10% of website traffic over last 3 months then that page is marked as Grade B. If a PAGE C was bringing 5% of website traffic over last 3 months then that page is marked as Grade C.

Next step is to investigate each page with the issue to understand why it is showing a drop. To do this we move towards the third objective and that is to identify the queries that are driving the drop. Now we map out each query page was ranking for and sort them with highest to lowest. Once again I perform the same test as we did on site-wide and page-level data. I calculate the impression and click drop rates for each query and sort them with highest to lowest. Queries with the highest drop rates are the ones that are driving the issue.

In order to identify the broader trend, identified queries with drop are analyzed to see if they are sharing the common theme (as in they are part of same cluster). If they are, then we can identify the broader trend and take appropriate action. Same test is done for identified pages with drop to see if they are part of same cluster (share a common theme)

## Comparison Rules

For now, I just have one comparison rule: data that is being compared should be of same magnitude. For example, if I am comparing impressions then both periods should have the same number of days.

## Segmentation Rules

I see Google Search Console data as a pyramid:

- Website as a whole
- Pages as individual units of that website
- Queries as individual units of each page

Clusters are identified by shared themes or patterns in the data. There are two types of clusters: 

- Query clusters: Queries that share a common theme or pattern.
- Page clusters: Pages that share a common theme or pattern.

## Evidence Rules

Retrieve at least 3 months of historical data when available to establish context. The default performance comparison is the most recent complete 28-day period versus the immediately preceding 28-day period.

## Interpretation Rules

The four core GSC metrics — Clicks, Impressions, CTR, and Position —
should not be interpreted independently. A change in one metric should
be interpreted in the context of the others.

Clicks and Impressions are the primary metrics for identifying
performance changes. CTR and Position are supporting metrics that help
explain the observed change.

### 1. Clicks ↓ + Impressions ↓

Interpretation:
The website/page/query is receiving less organic search visibility and
less organic traffic.

This is a meaningful negative performance signal, particularly when
both metrics decline beyond the defined threshold.

Position should then be examined:

- Position ↓ (worse): Ranking loss may be contributing to the decline.
- Position stable: The decline may be related to reduced search demand,
  loss of visibility across queries, SERP changes, or another factor.
- Position ↑ (better): Rankings improved despite lower visibility,
  suggesting that the decline cannot be explained by ranking loss alone.

Do not claim the underlying cause without additional evidence.


### 2. Clicks ↓ + Impressions Stable/↑

Interpretation:
Search visibility has remained stable or increased, but that visibility
is generating fewer clicks.

Examine CTR:

- CTR ↓: The decline in clicks is associated with a lower rate of
  searchers clicking the result.
- CTR stable: Investigate whether the change is concentrated in
  particular queries, pages, devices, countries, or other segments.

Position should also be considered because ranking changes can influence
CTR.

This pattern should not automatically be interpreted as a loss of
search visibility.


### 3. Clicks ↑ + Impressions ↑

Interpretation:
This is generally a positive performance signal. The website/page/query
is appearing more often in search and receiving more organic traffic.

Examine Position and CTR to understand the nature of the improvement:

- Position ↑ may indicate improved rankings contributing to growth.
- CTR ↑ indicates that a greater proportion of impressions are turning
  into clicks.
- Stable Position and CTR with higher Impressions may indicate broader
  search visibility or increased search demand.

Do not assume the cause of growth without supporting evidence.


### 4. Clicks ↑ + Impressions Stable/↓

Interpretation:
The website/page/query is generating more traffic without receiving more
search impressions.

Examine CTR:

- CTR ↑: Existing search visibility is converting into clicks more
  effectively.
- Position ↑: Improved rankings may be contributing to the higher CTR
  and click growth.

This can represent improved organic efficiency even if overall search
visibility has not increased.


### 5. Impressions ↑ + Clicks Stable

Interpretation:
Search visibility is increasing, but the additional impressions are not
producing proportional traffic growth.

Examine CTR and Position.

A falling CTR may indicate that the new impressions are coming from
lower-ranking positions, different queries, or search contexts that
generate fewer clicks.

Do not automatically treat increasing impressions as successful traffic
growth.


### 6. Impressions ↓ + Clicks Stable

Interpretation:
The website/page/query is maintaining approximately the same traffic
despite appearing less frequently in search.

Examine CTR and Position.

If CTR or Position improved, stronger performance on the remaining
impressions may be compensating for the loss of visibility.


### Position

Position is a supporting diagnostic metric rather than the primary
measure of performance.

- Improving Position can help explain increasing clicks or CTR.
- Worsening Position can help explain declining clicks or CTR.
- Average Position should not be used alone to conclude that performance
  improved or declined.

Changes in query mix can change average position even when individual
query rankings have not meaningfully changed.


### CTR

CTR is also a supporting diagnostic metric.

CTR describes how efficiently impressions convert into clicks.

- CTR ↑ means a greater proportion of impressions generated clicks.
- CTR ↓ means a smaller proportion of impressions generated clicks.

CTR changes should always be interpreted alongside Impressions and
Position rather than independently.

### General Rule

Never infer an underlying SEO root cause from a single metric.

First identify what changed using Clicks and Impressions. Then use CTR
and Position to better understand the pattern.

If GSC data identifies where a decline occurred but does not provide
enough evidence to explain why it occurred, report the observed pattern
and state that additional investigation is required.

## Common Traps

Low or no data does not mean there is issue with pipeline integration it could mean that the data is not being collected or is being filtered out. Or that site actually has no search visibility.

## Insufficient Evidence / Escalation Rules

GSC monitoring can identify whether performance changed and where the
change is concentrated, but it may not establish the underlying cause.

Do not claim a root cause without sufficient evidence.

If the investigation identifies a decline but GSC data cannot explain
why it occurred:

- state what the GSC evidence shows;
- state what remains unknown;
- identify what additional evidence would be needed;
- stop the investigation rather than guessing.

Potential additional evidence may include technical crawl data,
SERP analysis, GA4 data, page/content changes, indexing information,
competitor data, or other relevant sources.

## Output Expectations

Final result should be in the following format:

- Summary: A brief summary of the comparison, including the number of pages and queries analyzed, and any notable trends or patterns.
- Detailed Analysis: A breakdown of the comparison, including the specific pages and queries that were analyzed, and any notable trends or patterns.
- Conclusion: A summary of the comparison, including any notable trends or patterns, and any recommendations for further analysis.
