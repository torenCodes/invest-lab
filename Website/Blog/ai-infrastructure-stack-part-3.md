# The AI Factory, Part 3: The Power Crisis — Why the Grid Became the Real Bottleneck

*Published August 13, 2026*

---

In Part 2 we went into the engine room and looked at the chip, the CUDA moat, the custom silicon wave, and the single foundry in Taiwan that everything ultimately depends on. That layer still gets most of the attention, and it probably always will, because a GPU is a product you can hold up on a stage.

The problem is that the chip stopped being the hard part, because accelerators are something you can actually buy today. What you cannot reliably buy is a place to plug them in, and that has quietly become the defining constraint on how fast artificial intelligence can actually scale. The industry spent three years asking whether there were enough chips, and it is now spending 2026 discovering that the answer barely matters if the electricity, the transformers, and the substation capacity are not there to meet them.

This is the part of the stack where physics and permitting collide, and it moves at a very different speed than semiconductors.

---

## The Demand Stopped Being a Forecast

For a long time the power story was told in projections, which made it easy to wave away as the usual analyst enthusiasm. That is no longer where we are, because the load is showing up on real utility interconnection requests and in real capital plans.

AI is expected to draw on the order of 70 terawatt-hours of electricity in 2026, which is roughly what a country like Austria or Finland consumes in a year. The International Energy Agency projects that total data center demand more than doubles to around 945 terawatt-hours by 2030, and the growth is attributed almost entirely to AI rather than to conventional cloud workloads. In the United States, data centers currently account for something like 3 to 4 percent of national electricity consumption, and credible forecasts put that figure at 8 to 12 percent by the end of the decade.

The shape of the demand matters as much as the size of it. A modern AI campus is not a diffuse load spread politely across a region, it is a single site asking for somewhere between 100 and 750 megawatts in one place, on one interconnection, often in a county that has never seen a request remotely like it. That concentration is what turns a manageable national trend into a series of local emergencies, and it explains why the fight over AI power is being waged in county commission meetings rather than in Washington.

---

## The Bottleneck Moved, and Most People Missed It

Here is the part that gets misunderstood most often. The constraint is not that America cannot generate enough electricity, because in aggregate the generation can be built. The constraint is everything that sits between a generator and a server rack, and that middle layer has become the slowest-moving piece of the entire AI buildout.

Interconnection queues across the country now hold something in the neighborhood of 2,600 gigawatts of proposed generation and storage, which is far more capacity than the grid operators can study, approve, and energize on any reasonable timeline. Wait times of five years or more have become normal rather than exceptional.

What is genuinely new in 2026 is where the delay now lives. The queue itself is no longer the worst of it, because projects are increasingly spending more time waiting *after* they have been approved than they spent getting approved in the first place. PJM, the grid operator covering much of the mid-Atlantic and the largest data center corridor in the world, reports that projects average more than three years to reach an interconnection service agreement and then roughly another four years before they actually come online. Seven years from request to electrons is not a scenario, it is the current baseline in the region where the most AI capacity wants to be built.

---

## The Least Glamorous Object in the Stack

If you want a single physical object that explains the delay, it is the large power transformer, which is the least discussed and arguably most important component in this entire series.

Substation transformer lead times ran around 140 weeks in 2023, stretched to roughly 150 weeks in 2025, and now exceed 160 weeks in 2026. That is more than three years of waiting for a piece of equipment that no data center can operate without, and the trend has been moving in the wrong direction for the better part of a decade. The United States imports roughly 80 percent of this equipment, so the shortage is not something a single domestic factory announcement resolves quickly, and estimates of the overall supply deficit sit near 30 percent.

The consequences are already visible in the construction numbers rather than in the press releases. Industry estimates suggest that somewhere between 30 and 50 percent of planned 2026 data center openings will slip or be canceled outright, and of roughly 16 gigawatts of announced capacity, only about 5 gigawatts is actually under construction. The gap between what has been announced and what is being built is the single most useful thing to watch in this sector, because announcements are free and substations are not.

---

## Gas Is Winning the Next Five Years

Faced with a grid that cannot connect them quickly, the hyperscalers have made a pragmatic choice, and that choice is overwhelmingly natural gas for the near term. Gas turbines can be sited relatively quickly, they run around the clock without weather risk, and the technology carries none of the regulatory novelty that slows nuclear down.

The clearest evidence sits in GE Vernova's order book. The company's gas turbine backlog reached roughly 116 gigawatts by the second quarter of 2026, up from about 100 gigawatts in the first quarter, and management has talked about ending the year with something closer to 125 gigawatts under contract. Against annualized heavy-duty output running near 20 gigawatts, a backlog of that size represents five years of production that is already committed before a single new order arrives.

In practical terms the turbines are sold out through 2030, and the pricing reflects it, with 2026 orders reportedly landing 10 to 20 points above where fourth quarter 2025 orders were priced. When a capital goods manufacturer can raise prices that aggressively into a multi-year backlog, it is telling you the buyer has no real alternative, and that is a more honest read on scarcity than any demand forecast.

---

## Nuclear Is Real, and Nuclear Is Slow

Nuclear has become the headline energy story of the AI era, and the commitments behind those headlines are genuinely large. The four biggest hyperscalers have collectively committed to more than 9.8 gigawatts of nuclear capacity across roughly 13 announced deals, which would have seemed fanciful only a few years ago.

Microsoft anchored the trend with an 835 megawatt power purchase agreement tied to the restart of Three Mile Island Unit 1, a twenty year arrangement reported in the neighborhood of 16 billion dollars. Google committed to 500 megawatts from Kairos Power, Amazon put roughly 700 million dollars into X-energy with an eye toward as many as twelve Xe-100 small modular reactors, and Meta has assembled the largest portfolio of all at up to 6.6 gigawatts spread across TerraPower, Oklo, Vistra, and Constellation.

Now the sobering part, and it is the number that should anchor how you think about this entire category. As of July 2026, only about 19.6 percent of that committed nuclear power is actually flowing. The Three Mile Island restart is targeted for the second half of 2027, and meaningful small modular reactor deployment in the West does not begin in earnest until 2029 and continues rolling out into the mid 2030s. First-of-a-kind SMR costs are still running somewhere between 80 and 150 dollars per megawatt-hour against vendor targets of 60 to 80 dollars for later units, which means the economics improve only after the industry has built enough of them to learn.

Nuclear is the right answer for the 2030s and it does very little for 2027. Both things are true at once, and conflating them is the most common mistake in this discussion.

---

## Going Around the Grid Entirely

When the front door takes seven years, people start looking for another way in, and in this case that means generating power on site and skipping the interconnection process altogether. Behind-the-meter generation has moved from a niche workaround to something closer to a default design assumption, with projections of roughly 25 to 35 gigawatts of deployment through 2030.

The appeal is obvious, because a developer who builds their own generation controls their own schedule and sidesteps both the queue and the local rate debate. The tradeoff is less obvious and more interesting, since analysis from Utility Dive and others suggests that data centers running on-site gas plants may end up raising consumer energy bills *more* than if those same facilities had simply connected to the grid and paid for the upgrades. Self-supply removes a large customer from the base that funds shared infrastructure, and everyone still connected picks up a larger share of the fixed costs.

---

## The Risk That Is Not in Anyone's Model

The financial models for this buildout are generally very good at supply chains and very bad at politics, which is a problem, because the political constraint is tightening faster than the physical one.

Public resistance to data centers escalated sharply through the first half of 2026. More projects were rejected or canceled in the first quarter of 2026 alone than in all of 2025, at least eleven states are weighing legislation that would temporarily halt new data center construction while the effects on electricity prices are studied, and there are now local officials who have lost their seats over approving these projects. That is a meaningfully different environment than the one these capital plans were drawn up in.

The irony is that the underlying economics are genuinely contested. A 2026 study from the Electric Power Research Institute found that data centers pushed average retail rates modestly *down*, since large industrial customers help spread fixed costs across more kilowatt-hours. The Dallas Fed, meanwhile, expects the buildout to raise the electricity component of PCE inflation. Both findings can coexist depending on how the interconnection costs are allocated and who ends up paying for the upgrades, and that allocation question is exactly what the political fight is about.

For an investor the takeaway is not that the buildout stops, because it will not. The takeaway is that siting risk and regulatory risk now deserve a real place in the analysis, particularly for developers concentrated in a small number of hostile jurisdictions.

---

## Who Actually Benefits

Part 2 ended with a promise to look at the companies positioned to benefit, and the honest answer is that the clearest beneficiaries are not the ones generating the electricity. They are the ones manufacturing and installing the equipment that moves it, because that is where the scarcity is most acute and the pricing power is most durable.

Eaton sits closest to the chokepoint as a leading supplier of switchgear and transformers connecting the grid to the rack, and its reported United States data center backlog of roughly 307 gigawatts represents something like fifteen years of work at current build rates. The company is putting about 1.2 billion dollars into capacity expansion, which is a reasonable proxy for how long it expects the shortage to last.

Vertiv occupies the power and thermal management layer inside the building, and its project backlog more than doubled to above 15 billion dollars alongside 24 percent revenue growth and 925 million dollars of free cash flow in the second quarter of 2026. Quanta Services is the contractor that physically builds the transmission lines and substations, with a first quarter 2026 backlog of roughly 48.5 billion dollars and revenue up 26 percent year over year.

Behind all of them sits GE Vernova with the turbine order book described above, along with the independent power producers and utilities such as Constellation and Vistra that own existing generation the hyperscalers want to contract against. Owning power that already exists turned out to be a far better position than promising power that has to be built.

---

## What the Lab's Own Data Says Right Now

One advantage of running the dashboards on this site is that the thesis can be checked against live positioning rather than argued in the abstract, so here is what the Sector Rotation engine on the Movers and Shakers dashboard shows as of this writing.

The overall posture reads risk-on, and the two strongest sectors relative to the S&P 500 over the past month are Technology and Energy, both of which sit in the Leading quadrant of the rotation map. Energy outperforming by roughly 3.6 points while the market is in a risk-on stance is consistent with everything above, since gas is the near-term answer and the fuel side is getting paid first.

Utilities is the more interesting reading and the one worth watching. It is the weakest sector on the board over the past month at roughly 7 points behind the S&P 500, and yet it has rotated into the Improving quadrant, meaning relative momentum has turned up from a weak base even though the trailing numbers still look poor. That is often what the early stage of a rotation looks like, and it fits a market that is beginning to price regulated utilities as beneficiaries of load growth rather than as bond substitutes.

None of that is a recommendation, and rotation readings change from week to week. It is simply a useful discipline to hold a macro thesis up against what money is actually doing, because the two disagree more often than anyone would like.

---

## The Bottom Line

The AI story has quietly changed shape. For three years the question was whether enough compute could be manufactured, and the answer turned out to be yes. The question now is whether enough electricity can be delivered to a specific patch of ground on a specific date, and that answer depends on transformer factories, interconnection studies, turbine slots, and county commissioners rather than on anything happening in a chip fab.

That reframing is worth internalizing, because it changes where the constraint sits and therefore where the pricing power sits. The scarce resource in this phase is not intelligence and it is not silicon, it is interconnected, dispatchable, permitted power. Anyone who can supply it, move it, or build the equipment that carries it is negotiating from a position that will hold for years rather than quarters.

Next up in **Part 4**: cooling at scale. All of that electricity turns into heat, air cooling has run out of room, and the race to liquid is reshaping what a data center physically looks like. We will look at the technologies competing to solve it and the companies with real exposure to the transition.

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
