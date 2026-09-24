# The AI Factory, Part 3: The Power Crisis — Why the Grid Became the Real Bottleneck

*Published August 13, 2026*

---

In [Part 2](blog.html?post=ai-infrastructure-stack-part-2) we went into the engine room and looked at the chip, the CUDA moat, the custom silicon wave, and the single foundry in Taiwan that everything ultimately depends on. That layer still gets most of the attention, and it probably always will. A GPU is a product you can hold up on a stage.

The chip has stopped being the hard part, though. You can buy accelerators today. What you can't reliably buy is a place to plug them in, and that has become the defining constraint on how fast artificial intelligence can actually scale. The industry spent three years asking whether there were enough chips. In 2026 it's discovering that the answer barely matters if the electricity, the transformers and the substation capacity aren't there to meet them.

This is the part of the stack where physics and permitting collide, and it moves at a very different speed than semiconductors.

---

## The Demand Stopped Being a Forecast

For a long time the power story was told in projections, which made it easy to wave away as the usual analyst enthusiasm. Not anymore. The load is showing up in real utility interconnection requests and real capital plans.

AI is expected to draw on the order of 70 terawatt-hours of electricity in 2026, roughly what a country like Austria or Finland uses in a year. The International Energy Agency projects that total data center demand more than doubles to around 945 terawatt-hours by 2030, with almost all of that growth coming from AI. In the United States, data centers currently account for something like 3 to 4 percent of national electricity consumption, and credible forecasts put that figure at 8 to 12 percent by the end of the decade.

The shape of the demand matters as much as its size. A modern AI campus is a single site asking for somewhere between 100 and 750 megawatts in one place, on one interconnection, often in a county that has never seen a request anything like it. That concentration turns a manageable national trend into a string of local emergencies. It's also why the fight over AI power is playing out in county commission meetings instead of in Washington.

---

## The Bottleneck Moved, and Most People Missed It

This is the part that gets misunderstood most often. In aggregate, America can build enough generation. The constraint is everything that sits between a generator and a server rack, and that middle layer has become the slowest-moving piece of the entire AI buildout.

Interconnection queues across the country now hold something in the neighborhood of 2,600 gigawatts of proposed generation and storage, far more capacity than grid operators can study, approve and energize on any reasonable timeline. Waits of five years or more are now normal.

What's new in 2026 is where the delay lives. Projects increasingly spend more time waiting *after* they've been approved than they spent getting approved in the first place. PJM, the grid operator covering much of the mid-Atlantic and the largest data center corridor in the world, reports that projects average more than three years to reach an interconnection service agreement, then roughly another four years before they actually come online. Seven years from request to electrons is the current baseline in the region where the most AI capacity wants to be built.

---

## The Least Glamorous Object in the Stack

If you want a single physical object that explains the delay, it's the large power transformer, the least discussed and arguably most important component in this entire series.

Substation transformer lead times ran around 140 weeks in 2023, stretched to roughly 150 weeks in 2025, and now exceed 160 weeks in 2026. That's more than three years of waiting for a piece of equipment no data center can operate without, and the trend has been heading the wrong way for the better part of a decade. The United States imports roughly 80 percent of this equipment, so one domestic factory announcement won't fix the shortage quickly. Estimates of the overall supply deficit sit near 30 percent.

The consequences already show up in the construction numbers. Industry estimates suggest that somewhere between 30 and 50 percent of planned 2026 data center openings will slip or be canceled outright, and of roughly 16 gigawatts of announced capacity, only about 5 gigawatts is actually under construction. The gap between what's been announced and what's being built is the single most useful thing to watch in this sector. Announcements are free. Substations aren't.

---

## Gas Is Winning the Next Five Years

Faced with a grid that can't connect them quickly, the hyperscalers have made a pragmatic choice, and for the near term that choice is overwhelmingly natural gas. Gas turbines can be sited relatively quickly, they run around the clock without weather risk, and the technology carries none of the regulatory novelty that slows nuclear down.

The clearest evidence is GE Vernova's order book. Its gas turbine backlog reached roughly 116 gigawatts by the second quarter of 2026, up from about 100 gigawatts in the first quarter, and management has talked about ending the year with something closer to 125 gigawatts under contract. Against annualized heavy-duty output running near 20 gigawatts, a backlog that size is five years of production already committed before a single new order arrives.

In practical terms the turbines are sold out through 2030, and the pricing shows it, with 2026 orders reportedly landing 10 to 20 points above where fourth quarter 2025 orders were priced. When a capital goods maker can raise prices that aggressively into a multi-year backlog, it's telling you the buyer has no real alternative. Pricing like that is a more honest read on scarcity than any demand forecast.

---

## Nuclear Is Real, and Nuclear Is Slow

Nuclear has become the headline energy story of the AI era, and the commitments behind those headlines are large. The four biggest hyperscalers have collectively committed to more than 9.8 gigawatts of nuclear capacity across roughly 13 announced deals, which would have seemed fanciful only a few years ago.

Microsoft anchored the trend with an 835 megawatt power purchase agreement tied to the restart of Three Mile Island Unit 1, a twenty year arrangement reported in the neighborhood of 16 billion dollars. Google committed to 500 megawatts from Kairos Power, Amazon put roughly 700 million dollars into X-energy with an eye toward as many as twelve Xe-100 small modular reactors, and Meta has assembled the largest portfolio of all, at up to 6.6 gigawatts spread across TerraPower, Oklo, Vistra and Constellation.

Now the sobering number. As of July 2026, only about 19.6 percent of that committed nuclear power is actually flowing. The Three Mile Island restart is targeted for the second half of 2027, and meaningful small modular reactor deployment in the West doesn't begin in earnest until 2029, continuing to roll out into the mid 2030s. First-of-a-kind SMR costs are still running somewhere between 80 and 150 dollars per megawatt-hour, against vendor targets of 60 to 80 dollars for later units. The economics only improve once the industry has built enough of them to learn.

Nuclear is the right answer for the 2030s and does very little for 2027. Mixing up those two timelines is the most common mistake in this discussion.

---

## Going Around the Grid Entirely

When the front door takes seven years, people start looking for another way in. Here that means generating power on site and skipping the interconnection process altogether. Behind-the-meter generation has gone from a niche workaround to something close to a default design assumption, with projections of roughly 25 to 35 gigawatts of deployment through 2030.

The appeal is obvious. A developer who builds its own generation controls its own schedule and sidesteps both the queue and the local rate debate. The tradeoff is less obvious and more interesting. Analysis from Utility Dive and others suggests that data centers running on-site gas plants may end up raising consumer energy bills *more* than if those same facilities had simply connected to the grid and paid for the upgrades. Self-supply pulls a large customer out of the base that funds shared infrastructure, and everyone still connected picks up a bigger share of the fixed costs.

---

## The Risk That Is Not in Anyone's Model

The financial models for this buildout are generally very good at supply chains and very bad at politics. That's a problem, because the political constraint is tightening faster than the physical one.

Public resistance to data centers escalated sharply through the first half of 2026. More projects were rejected or canceled in the first quarter of 2026 alone than in all of 2025. At least eleven states are weighing legislation that would temporarily halt new data center construction while the effects on electricity prices are studied, and some local officials have already lost their seats over approving these projects. It's a very different environment from the one these capital plans were drawn up in.

The irony is that the underlying economics are contested. A 2026 study from the Electric Power Research Institute found that data centers pushed average retail rates modestly *down*, since large industrial customers spread fixed costs across more kilowatt-hours. The Dallas Fed, meanwhile, expects the buildout to raise the electricity component of PCE inflation. Both findings can hold depending on how interconnection costs are allocated and who ends up paying for the upgrades, and that allocation question is exactly what the political fight is about.

The buildout won't stop. What changes for an investor is that siting risk and regulatory risk now deserve a real place in the analysis, particularly for developers concentrated in a small number of hostile jurisdictions.

---

## Who Actually Benefits

Part 2 ended with a promise to look at the companies positioned to benefit. The clearest beneficiaries turn out to be the ones manufacturing and installing the equipment that moves electricity, more so than the ones generating it. That's where the scarcity is most acute and the pricing power most durable.

Eaton sits closest to the chokepoint as a leading supplier of the switchgear and transformers connecting the grid to the rack. Its reported United States data center backlog of roughly 307 gigawatts represents something like fifteen years of work at current build rates. The company is putting about 1.2 billion dollars into capacity expansion, which is a reasonable proxy for how long it expects the shortage to last.

Vertiv covers the power and thermal management layer inside the building. Its project backlog more than doubled to above 15 billion dollars, alongside 24 percent revenue growth and 925 million dollars of free cash flow in the second quarter of 2026. Quanta Services is the contractor that physically builds the transmission lines and substations, with a first quarter 2026 backlog of roughly 48.5 billion dollars and revenue up 26 percent year over year.

Behind all of them sits GE Vernova and the turbine order book above, along with independent power producers and utilities such as Constellation and Vistra that own existing generation the hyperscalers want to contract against. Owning power that already exists turned out to be a far better position than promising power that still has to be built.

---

## What the Lab's Own Data Says Right Now

One advantage of running the dashboards on this site is that the argument can be checked against live positioning. Here's what the Sector Rotation engine on the Movers & Shakers dashboard shows as of this writing.

The overall posture reads risk-on, and the two strongest sectors relative to the S&P 500 over the past month are Technology and Energy, both sitting in the Leading quadrant of the rotation map. Energy outperforming by roughly 3.6 points in a risk-on market fits everything above: gas is the near-term answer, and the fuel side is getting paid first.

Utilities is the more interesting reading. It's the weakest sector on the board over the past month, at roughly 7 points behind the S&P 500, yet it has rotated into the Improving quadrant. That means relative momentum has turned up from a weak base even though the trailing numbers still look poor. It's often what the early stage of a rotation looks like, and it fits a market that's starting to price regulated utilities as beneficiaries of load growth instead of as bond substitutes.

None of that is a recommendation, and rotation readings change from week to week. It's simply a useful discipline to hold a macro argument up against what money is actually doing, because the two disagree more often than anyone would like.

---

## The Bottom Line

The AI story has changed shape. For three years the question was whether enough compute could be manufactured, and the answer turned out to be yes. The question now is whether enough electricity can be delivered to a specific patch of ground on a specific date. That depends on transformer factories, interconnection studies, turbine slots and county commissioners, and very little on anything happening in a chip fab.

That moves the constraint, and with it the pricing power. The scarce resource in this phase is interconnected, dispatchable, permitted power. Anyone who can supply it, move it or build the equipment that carries it is negotiating from a position that will hold for years.

Next up in **Part 4**: cooling at scale. All of that electricity turns into heat, air cooling has run out of room, and the race to liquid is reshaping what a data center physically looks like. We'll look at the technologies competing to solve it and the companies with real exposure to the transition.

---

**Key companies mentioned in this post:**

| Company | Ticker | Role |
|---------|--------|------|
| GE Vernova | GEV | Gas turbines, grid equipment, electrification |
| Eaton | ETN | Switchgear and transformers, grid-to-rack power |
| Vertiv | VRT | Data center power and thermal management |
| Quanta Services | PWR | Transmission line and substation construction |
| Constellation Energy | CEG | Nuclear generation, hyperscaler PPAs |
| Vistra | VST | Independent power producer, nuclear and gas |
| Oklo | OKLO | Advanced fission, Meta partnership |
| NuScale Power | SMR | Small modular reactor developer |
| Talen Energy | TLN | Independent power producer, data center PPAs |
| Siemens Energy | ENR.DE | Grid equipment and turbines |

---

*This post is for informational and educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
