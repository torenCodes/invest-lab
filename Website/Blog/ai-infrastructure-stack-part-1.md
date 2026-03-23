# The AI Factory, Part 1: A Ground-Up Look at Everything That Powers Artificial Intelligence

*Published March 20, 2026*

---

When most people think about AI, they picture a chatbot on their phone or a model generating images. What they don't picture is what it actually takes to make that happen: a physical factory the size of multiple city blocks, drawing more electricity than a small town, running 24 hours a day, cooled by enough water to fill an Olympic swimming pool every single day.

The buildout behind AI is one of the most ambitious engineering projects in human history. And unlike software, you can't scale it with a few lines of code. Every layer of this stack, from the raw materials pulled from the earth to the power lines feeding a campus, has to be physically designed, manufactured, and maintained.

This is Part 1 of a series breaking down exactly what goes into an AI data center. Not to overwhelm, but to demystify. Once you understand the ingredients, a lot of what's happening in the markets and in the news starts to make considerably more sense.

Let's start from the beginning.

---

## Layer 1: The Chip

Everything traces back to the chip. At the heart of an AI data center is a GPU (Graphics Processing Unit), originally designed for video game graphics and repurposed into the workhorse of AI. NVIDIA's H100 and the newer Blackwell GPUs are the household names. AMD is a real competitor. But the chip conversation is almost beside the point here — that story is already well-covered.

What's less understood is what these chips demand of everything around them.

A single modern AI chip can draw over 1,000 watts of power (roughly ten 100-watt light bulbs) from a piece of silicon the size of your palm. A full rack of these systems can consume 120 kilowatts or more. Scale that to a large training cluster running thousands of chips and you're talking about electricity loads that rival small cities.

Beyond raw GPUs, the biggest tech companies are also building their own custom chips. Google has its TPUs (Tensor Processing Units). Amazon built Trainium for training and Inferentia for running models. Meta has MTIA chips. Microsoft is working on Maia silicon. These custom ASICs (Application-Specific Integrated Circuits) are designed to do one thing, AI compute, more efficiently than a general-purpose GPU. Broadcom and Marvell are the two companies most often hired to design and build them for hyperscalers.

Nearly all of these chips, custom or otherwise, are manufactured by TSMC — Taiwan Semiconductor Manufacturing Company. TSMC doesn't design chips; it fabricates them. It is the single most important chokepoint in the entire global semiconductor supply chain.

**Key companies:** NVIDIA (NVDA), AMD, Broadcom (AVGO), Marvell (MRVL), TSMC (TSM)

---

## Layer 2: The Substrate — The Materials Under the Silicon

Not everything in an AI system is made of plain silicon. The most demanding components, the ones pushing the limits of speed and efficiency, rely on compound semiconductors, materials with names that sound like a chemistry exam: indium phosphide (InP), gallium arsenide (GaAs), gallium nitride (GaN).

These exotic materials exist because silicon has limits. At very high frequencies and in optical applications, it hits a wall. These other materials break through it.

Indium phosphide is particularly critical. It's what the lasers inside optical transceivers are built from. Without InP, the high-speed optical networking that connects AI clusters simply doesn't exist. GaN, meanwhile, is increasingly used in power electronics, converting AC power from the grid to the DC power that chips need, with far higher efficiency than older silicon-based components. In a world where AI data centers consume hundreds of megawatts, even a few percentage points of efficiency improvement adds up fast.

The companies that grow and process these substrates sit at the very base of the supply chain. They don't get much attention, but they're not replaceable.

**Key companies:** AXT Inc. (AXTI — InP, GaAs, and germanium substrates), Coherent (COHR — vertically integrated through InP), Wolfspeed (WOLF — GaN power semiconductors), IQE (IQE.L — epitaxial wafers, UK-listed)

---

## Layer 3: Copper — The Unglamorous Workhorse

Before data goes anywhere over fiber, it travels short distances over copper. Inside a server, between chips on a board, between a server and a nearby switch — copper handles the last inch of connectivity. Direct Attach Cables (DACs), the PCBs inside every server, the connectors and backplanes in every rack — all copper.

It doesn't get much press in the AI narrative, but the sheer volume being consumed is staggering. AI racks are far denser and more interconnected than anything that came before them. More density means more traces, more connectors, more cabling.

There's also the power delivery side of this. Getting 120+ kilowatts into a single rack requires robust copper busbars (thick copper bars that distribute power throughout the rack) and sophisticated distribution infrastructure. This is a genuine engineering challenge that data center designers didn't have to solve at this scale before AI arrived.

At higher speeds, raw copper hits bandwidth limits. Companies like Credo Technology build specialized chips called SerDes (Serializer/Deserializer) that extend how far and how fast copper can carry a signal, buying time before fiber takes over entirely.

**Key companies:** Amphenol (APH), TE Connectivity (TEL), Credo Technology (CRDO), Belden (BDC)

---

## Layer 4: Photonics — Moving Data at the Speed of Light

Copper works fine for short distances. For anything longer (between racks, between rows of servers, between buildings, between data centers) it doesn't hold up. Signal degrades, power consumption climbs, and bandwidth caps out. That's where photonics comes in.

Photonics is the technology of moving information using light instead of electrons. An optical transceiver sits at the end of a fiber cable and handles the conversion: electrical signal in, laser light out, and vice versa on the receiving end. The fiber itself is glass: incredibly thin strands that carry pulses of light across any distance with minimal signal loss.

As AI clusters scaled from hundreds of GPUs to tens of thousands, demand for high-speed transceivers exploded. We're currently mid-transition from 400G (400 gigabits per second) to 800G, with 1.6T on the horizon. Each generation requires new transceivers, new switches, new fiber plant. It's a recurring capital upgrade cycle, not a one-time build.

The supply chain here runs deep. InP substrates (AXTI) feed into component manufacturers (COHR, LITE) who make lasers and photodetectors. Those go into transceivers assembled by contract manufacturers (FN, AAOI). The transceivers plug into networking systems (CIEN, MRVL). Every link in that chain is seeing demand it's never seen before.

We covered this in more depth in *The Fiber Backbone of AI* and will go deeper still in a future part of this series.

**Key companies:** Coherent (COHR), Lumentum (LITE), Fabrinet (FN), Applied Optoelectronics (AAOI), Ciena (CIEN), Marvell (MRVL)

---

## Layer 5: Cooling — The Heat Problem Nobody Warned You About

AI data centers have a heat problem unlike anything the industry has faced before. This one tends to catch people off guard.

Traditional data centers used air cooling, basically large industrial air conditioners pushing cold air through rows of servers. That works fine up to a point. But when a single rack dissipates 120 kilowatts of heat, air physically can't carry it away fast enough. You'd need a wind tunnel running through every row.

So the industry is migrating to liquid cooling, and doing it fast. The two main approaches:

**Direct Liquid Cooling (DLC):** Cold plates attach directly to the processor chips, and water circulates through them, absorbing heat right at the source. NVIDIA's latest DGX systems are built around this.

**Immersion Cooling:** Entire servers are submerged in a special non-conductive liquid that absorbs heat from all components at once. More complex to operate, but increasingly practical for the highest-density deployments.

Water is a far better heat carrier than air. But it introduces new infrastructure requirements: cooling towers, heat exchangers, plumbing, water treatment. In dry climates, the water consumption itself becomes an environmental and permitting issue. Some of the largest data centers now negotiate water rights alongside power contracts.

**Key companies:** Vertiv (VRT), Modine Manufacturing (MOD), nVent Electric (NVT)

---

## Layer 6: Power — Feeding the Beast

Maybe the biggest physical constraint in this whole buildout is electricity.

A hyperscale AI data center can consume hundreds of megawatts. The largest campuses being planned today are heading toward gigawatt scale. That's the output of a large nuclear plant, dedicated to a single data center complex. Microsoft, Google, Amazon, and Meta have made commitments in the hundreds of billions of dollars, and a large share of that spending is simply acquiring and delivering electricity at unprecedented scale.

The ripple effects run up and down the power chain. The grid itself has to be upgraded: new transmission lines, substations, and transformers to move power from generation to campus. The US electrical grid was built decades ago and wasn't designed for this. Waiting for a new grid connection can take years, which has become one of the primary bottlenecks slowing data center construction right now.

Inside the data center, power has to be distributed through PDUs (Power Distribution Units), transformed to the right voltages, and managed carefully to protect hardware worth millions of dollars from fluctuations.

The source of generation is also becoming a strategic question. Hyperscalers are signing long-term contracts directly with nuclear plants. Microsoft famously struck a deal with Constellation Energy to restart Three Mile Island. They're also signing with utility-scale solar and wind. The carbon commitments aren't just PR. They're also why clean power sources are getting premium attention from some of the largest energy buyers on earth.

**Key companies:** Vertiv (VRT), Eaton (ETN), Schneider Electric (SBGSY), Constellation Energy (CEG), Quanta Services (PWR), MYR Group (MYRG)

---

## Layer 7: Backup Power — What Happens When the Grid Fails

Behind every data center is a UPS — Uninterruptible Power Supply — that bridges the gap when grid power is interrupted. Even a fraction of a second of downtime during an AI training run can corrupt a job that took days to complete.

Traditionally, UPS systems used heavy lead-acid batteries, the same basic chemistry as a car battery just at enormous scale. The industry is moving toward lithium-ion UPS systems, which are lighter, faster-charging, and survive more charge cycles before needing replacement.

Some of the largest facilities are also starting to explore using their battery banks as grid assets — charging during cheap off-peak hours and potentially selling power back during peak demand. It's still early, but it blurs the line between data center and power plant in a way worth keeping an eye on.

**Key companies:** EnerSys (ENS), Vertiv (VRT), Schneider Electric (SBGSY)

---

## The Big Picture

Zoom out and you see a supply chain that starts in a mine (copper, rare materials for compound semiconductors), runs through semiconductor fabs and photonic component factories, through data center cooling and electrical systems, all the way to a power plant and the transmission lines carrying electricity to a campus.

Every layer has companies fighting for position. Every layer is constrained in ways nobody anticipated three years ago. And every layer is seeing capital investment at a scale that is, genuinely, historic.

That's what makes the AI infrastructure story bigger than an Nvidia story. The GPU is the engine. But the engine needs fuel, cooling, a transmission, a chassis, and a road. All of that has to be built.

---

## What's Coming in This Series

We've done a flyover of the full stack. Upcoming parts will go deeper on individual layers:

- **Part 2:** The chip in detail — GPU architecture, custom ASICs, and why TSMC controls the world
- **Part 3:** The power crisis — how AI is reshaping the US electrical grid and the companies building the new infrastructure
- **Part 4:** Cooling at scale — the race from air to liquid and what it means for the companies solving the heat problem
- **Part 5:** The optical layer — photonics, InP, and the fiber connecting it all

Understanding what AI actually requires, layer by layer, is the foundation for understanding where the opportunities are.

---

*This post is for informational and educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
