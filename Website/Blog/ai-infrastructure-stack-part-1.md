# The AI Factory, Part 1: A Ground-Up Look at Everything That Powers Artificial Intelligence

*Published March 20, 2026*

---

When most people think about AI, they picture a chatbot on their phone or a model generating images. What they don't picture is what it takes to make that happen. It's a physical factory the size of several city blocks, drawing more electricity than a small town and running 24 hours a day. It's cooled by enough water to fill an Olympic swimming pool every single day.

The buildout behind AI is physical, and you can't scale it with a few lines of code. Every layer of this stack, from the raw materials pulled out of the earth to the power lines feeding a campus, has to be designed, manufactured and maintained.

This is Part 1 of a series breaking down exactly what goes into an AI data center, with the aim of demystifying it. Once you understand the ingredients, a lot of what's happening in the markets and the news starts to make more sense. Let's start at the bottom of the stack.

---

## Layer 1: The Chip

Everything traces back to the chip. At the heart of an AI data center is a GPU (Graphics Processing Unit), originally designed for video game graphics and repurposed into the workhorse of AI. NVIDIA's H100 and the newer Blackwell GPUs are the household names, and AMD is a real competitor pushing hard on its own roadmap. The chip race itself is almost beside the point here, since it's covered well everywhere else.

What's less understood is what these chips demand of everything around them.

A single modern AI chip can draw over 1,000 watts of power (roughly ten 100-watt light bulbs) from a piece of silicon the size of your palm. A full rack of these systems can consume 120 kilowatts or more. Scale that to a large training cluster running thousands of chips and you're talking about electricity loads that rival small cities.

Beyond GPUs, the biggest tech companies are building their own custom chips. Google has its TPUs (Tensor Processing Units), Amazon built Trainium for training and Inferentia for running models, Meta has its MTIA chips, and Microsoft is working on Maia silicon. These custom ASICs (Application-Specific Integrated Circuits) do one thing, AI compute, more efficiently than a general-purpose GPU. Broadcom and Marvell are the two companies most often hired to design and build them for the hyperscalers.

Nearly all of these chips, custom or otherwise, are manufactured by TSMC (Taiwan Semiconductor Manufacturing Company). TSMC doesn't design chips. It fabricates them for almost everyone who does, which makes it the single most important chokepoint in the global semiconductor supply chain.

**Key companies:** NVIDIA (NVDA), AMD, Broadcom (AVGO), Marvell (MRVL), TSMC (TSM)

---

## Layer 2: The Substrate Beneath the Silicon

Not everything in an AI system is made of plain silicon. The most demanding components, the ones pushing the limits of speed and efficiency, rely on compound semiconductors with names that sound like a chemistry exam: indium phosphide (InP), gallium arsenide (GaAs) and gallium nitride (GaN).

These exotic materials exist because silicon has limits. At very high frequencies and in optical applications it hits a wall, and these materials get past it.

Indium phosphide is especially critical. It's what the lasers inside optical transceivers are built from, and without InP the high-speed optical networking that connects AI clusters simply doesn't exist. GaN, meanwhile, is increasingly used in power electronics, converting AC power from the grid into the DC power chips need, far more efficiently than older silicon parts. When an AI data center consumes hundreds of megawatts, even a few percentage points of efficiency add up fast.

The companies that grow and process these substrates sit at the very base of the supply chain. They don't get much attention, and they can't easily be replaced.

**Key companies:** AXT Inc. (AXTI, InP, GaAs, and germanium substrates), Coherent (COHR, vertically integrated through InP), Wolfspeed (WOLF, GaN power semiconductors), IQE (IQE.L, epitaxial wafers, UK-listed)

---

## Layer 3: Copper, the Unglamorous Workhorse

Before data goes anywhere over fiber, it travels short distances over copper. Inside a server, between chips on a board, and between a server and a nearby switch, copper handles the last inch of connectivity. Direct Attach Cables (DACs), the PCBs inside every server, and the connectors and backplanes in every rack are all copper.

It barely registers in the AI narrative, but the sheer volume being consumed is staggering. AI racks are far denser and more interconnected than anything that came before them, and more density means more traces, more connectors and more cabling.

Then there's power delivery. Getting 120+ kilowatts into a single rack takes heavy copper busbars (thick copper bars that distribute power through the rack) and serious distribution infrastructure. Data center designers never had to solve that at this scale before AI arrived.

At higher speeds, raw copper runs into bandwidth limits. That's why companies like Credo Technology build specialized chips called SerDes (Serializer/Deserializer) that stretch how far and how fast copper can carry a signal, buying time before fiber takes over entirely.

**Key companies:** Amphenol (APH), TE Connectivity (TEL), Credo Technology (CRDO), Belden (BDC)

---

## Layer 4: Photonics, Moving Data at the Speed of Light

Copper works fine for short distances. For anything longer, whether that's between racks, between rows of servers, between buildings or between data centers, it struggles. The signal degrades, power consumption climbs and bandwidth caps out. That's where photonics comes in.

Photonics moves information with light instead of electrons. An optical transceiver sits at the end of a fiber cable and handles the conversion: electrical signal in, laser light out, and the reverse on the receiving end. The fiber itself is glass, incredibly thin strands that carry pulses of light across any distance with minimal signal loss.

As AI clusters scaled from hundreds of GPUs to tens of thousands, demand for high-speed transceivers exploded. We're in the middle of a transition from 400G (400 gigabits per second) to 800G, with 1.6T on the horizon, and each generation requires new transceivers, new switches and new fiber plant. Every step up is another round of spending.

The supply chain runs deep. InP substrates (AXTI) feed component makers (COHR, LITE) that build lasers and photodetectors. Those go into transceivers assembled by contract manufacturers (FN, AAOI), and the transceivers plug into networking systems (CIEN, MRVL). Every link in that chain is seeing demand it has never seen before.

We covered this in more depth in [*The Fiber Backbone of AI*](blog.html?post=optical-ai-infrastructure), and a later part of this series will go deeper still.

**Key companies:** Coherent (COHR), Lumentum (LITE), Fabrinet (FN), Applied Optoelectronics (AAOI), Ciena (CIEN), Marvell (MRVL)

---

## Layer 5: Cooling, the Heat Problem Nobody Warned You About

AI data centers have a heat problem the industry has never faced before, and it tends to catch people off guard.

Traditional data centers used air cooling, basically large industrial air conditioners pushing cold air through rows of servers. That works up to a point. When a single rack gives off 120 kilowatts of heat, though, air physically can't carry it away fast enough. You'd need a wind tunnel running through every row just to keep up.

So the industry is moving to liquid cooling, and fast. There are two main approaches.

**Direct Liquid Cooling (DLC):** Cold plates attach directly to the processor chips, and water circulates through them, absorbing heat right at the source. NVIDIA's latest DGX systems are built around this approach.

**Immersion Cooling:** Entire servers are submerged in a special non-conductive liquid that absorbs heat from every component at once. It's more complex to operate, but increasingly practical for the highest-density deployments.

Water carries heat far better than air, but it brings new infrastructure: cooling towers, heat exchangers, plumbing and water treatment. In dry climates the water use itself becomes an environmental and permitting issue, and some of the largest data centers now negotiate water rights alongside their power contracts.

**Key companies:** Vertiv (VRT), Modine Manufacturing (MOD), nVent Electric (NVT)

---

## Layer 6: Power, Feeding the Beast

The biggest physical constraint in this whole buildout may be electricity.

A hyperscale AI data center can consume hundreds of megawatts, and the largest campuses being planned today are heading toward gigawatt scale. That's roughly the output of a large nuclear plant, dedicated to a single data center complex. Microsoft, Google, Amazon and Meta have made commitments in the hundreds of billions of dollars, and a large share of that spending simply goes to acquiring and delivering electricity at unprecedented scale.

The ripple effects run up and down the power chain. The grid has to be upgraded with new transmission lines, substations and transformers to move power from generation to campus, and the US grid was built decades ago with nothing like this in mind. Waiting for a new grid connection can take years, which has become one of the main bottlenecks slowing data center construction right now.

Inside the data center, power has to be distributed through PDUs (Power Distribution Units), stepped to the right voltages and managed carefully to protect hardware worth millions of dollars from fluctuations.

Where the power comes from is becoming a strategic question too. Hyperscalers are signing long-term contracts directly with nuclear plants, most famously Microsoft's deal with Constellation Energy to restart Three Mile Island, alongside utility-scale solar and wind agreements. The carbon commitments behind those deals are real, and they're a big reason clean power is getting premium attention from some of the largest energy buyers on earth.

**Key companies:** Vertiv (VRT), Eaton (ETN), Schneider Electric (SBGSY), Constellation Energy (CEG), Quanta Services (PWR), MYR Group (MYRG)

---

## Layer 7: Backup Power, for When the Grid Fails

Behind every data center is a UPS (Uninterruptible Power Supply) that bridges the gap when grid power drops. Even a fraction of a second of downtime during an AI training run can corrupt a job that took days to complete.

UPS systems traditionally used heavy lead-acid batteries, the same basic chemistry as a car battery at enormous scale. The industry is moving to lithium-ion UPS systems, which are lighter, charge faster and survive more charge cycles before they need replacing.

Some of the largest facilities are also starting to use their battery banks as grid assets, charging during cheap off-peak hours and potentially selling power back during peak demand. It's early, but it starts to blur the line between a data center and a power plant.

**Key companies:** EnerSys (ENS), Vertiv (VRT), Schneider Electric (SBGSY)

---

## The Big Picture

Zoom out and you see a supply chain that starts in a mine (copper, and the rare materials behind compound semiconductors), runs through semiconductor fabs and photonic component factories, through data center cooling and electrical systems, and ends at a power plant and the transmission lines carrying electricity to a campus.

Each layer has companies fighting for position and constraints nobody saw coming three years ago, and each is absorbing capital on a genuinely historic scale.

That's what makes the AI infrastructure story bigger than an Nvidia story. The GPU is the engine, but an engine alone won't move anything without fuel, cooling, a transmission, a chassis and a road, and all of that has to be designed and built somewhere.

---

## The Rest of This Series

This was a flyover of the full stack. Each later part goes deeper on a single layer:

- **[Part 2: The Chip](blog.html?post=ai-infrastructure-stack-part-2).** GPU architecture, custom ASICs, and why TSMC controls the world.
- **[Part 3: The Power Crisis](blog.html?post=ai-infrastructure-stack-part-3).** How AI is reshaping the US electrical grid, and the companies building the new infrastructure.
- **Part 4: Cooling at scale** (coming next). The race from air to liquid, and what it means for the companies solving the heat problem.
- **Part 5: The optical layer** (planned). Photonics, InP, and the fiber connecting it all.

Understanding what AI actually requires, layer by layer, is the foundation for understanding where the opportunities are.

---

*This post is for informational and educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
