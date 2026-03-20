# The AI Factory, Part 1: A Ground-Up Look at Everything That Powers Artificial Intelligence

*Published March 20, 2026*

---

When most people think about AI, they picture a chatbot on their phone or a model generating images. What they don't picture is what it actually takes to make that happen: a physical factory the size of multiple city blocks, drawing more electricity than a small town, running 24 hours a day, seven days a week, cooled by enough water to fill an Olympic swimming pool every single day.

The buildout behind AI is one of the most ambitious engineering and infrastructure projects in human history. And unlike software, you can't scale it with a few lines of code. Every layer of this stack — from the raw materials pulled from the earth to the power lines feeding a campus — has to be physically designed, manufactured, and maintained.

This is Part 1 of a series that breaks down exactly what goes into an AI data center. Not to overwhelm, but to demystify. Because once you understand the ingredients, a lot of what's happening in the markets and in the news starts to make considerably more sense.

Let's start from the beginning.

---

## Layer 1: The Chip — Where It All Starts

Everything traces back to the chip. At the heart of an AI data center is a **GPU** — a Graphics Processing Unit — originally designed to render video game graphics and repurposed into the workhorse of AI. NVIDIA's H100 and the newer Blackwell GPUs are the household names. AMD is a real competitor. But the chip conversation is almost beside the point here — that story is already well-covered.

What's less understood is what these chips *demand* of everything around them.

A single modern AI chip can draw over **1,000 watts** of power — roughly the same as running ten 100-watt light bulbs — from a piece of silicon the size of your palm. A full rack of these systems can consume **120 kilowatts or more**. A large training cluster running thousands of them? We're talking electricity loads that rival small cities.

Beyond raw GPUs, the largest tech companies are also building their own custom chips. Google has its **TPUs** (Tensor Processing Units). Amazon built **Trainium** for training and **Inferentia** for running models. Meta has its **MTIA** chips. Microsoft is working on its **Maia** silicon. These custom ASICs (Application-Specific Integrated Circuits) are designed to do one thing — AI compute — more efficiently than a general-purpose GPU. Broadcom and Marvell are the two companies most often hired to design and build these custom chips for hyperscalers.

Nearly all of these chips, custom or otherwise, are manufactured by **TSMC** — Taiwan Semiconductor Manufacturing Company. TSMC doesn't design chips; it fabricates them. It is the single most critical chokepoint in the entire global semiconductor supply chain.

**Key companies:** NVIDIA (NVDA), AMD, Broadcom (AVGO), Marvell (MRVL), TSMC (TSM)

---

## Layer 2: The Substrate — The Materials Under the Silicon

Here's something that rarely makes headlines but matters enormously: not everything in an AI system is made of plain silicon. The most demanding components — the ones pushing the limits of speed and efficiency — rely on **compound semiconductors**, materials with names that sound like a chemistry exam: indium phosphide (InP), gallium arsenide (GaAs), gallium nitride (GaN).

Why do these exotic materials exist? Because silicon has limits. At very high frequencies, at optical applications, at extreme power densities, silicon hits a wall. These compound materials break through that wall.

**Indium phosphide (InP)** is particularly important for the lasers inside optical components — the devices that convert electrical signals into light pulses so data can travel through fiber optic cables. Without InP, the high-speed optical networking that connects AI clusters simply doesn't exist.

**Gallium nitride (GaN)** is increasingly used in power electronics — converting AC power from the grid to the DC power chips need, with far higher efficiency than older silicon-based power components. In a world where AI data centers are consuming hundreds of megawatts, even a few percentage points of efficiency gain matters enormously.

The companies that grow and process these semiconductor substrates sit at the very base of the supply chain — often overlooked, but impossible to replace.

**Key companies:** AXT Inc. (AXTI — InP, GaAs, and germanium substrates), Coherent (COHR — vertically integrated through InP), Wolfspeed (WOLF — GaN power semiconductors), IQE (IQE.L — epitaxial wafers, UK-listed)

---

## Layer 3: Copper — The Unglamorous Workhorse

Before data travels anywhere over fiber, it moves short distances over copper. Inside a server, between chips on a board, between a server and a nearby switch — copper handles the "last inch" of connectivity. **Direct Attach Cables (DACs)**, the printed circuit boards (PCBs) inside every server, the connectors and backplanes in every rack — all copper.

Copper doesn't get glamorous press in the AI narrative, but the volume being consumed is staggering. AI racks are far denser and more interconnected than anything that came before them. More density means more traces, more connectors, more cabling.

There's also the power delivery dimension. Getting 120+ kilowatts into a single rack requires extremely robust copper **busbars** — thick copper bars that distribute power throughout the rack — and sophisticated power distribution infrastructure. This is a real engineering challenge that data center designers didn't face at this scale before AI arrived.

At higher speeds, raw copper hits bandwidth limits. Companies like **Credo Technology** build specialized chips called SerDes (Serializer/Deserializer) that extend how far and how fast copper can carry a signal — buying time before fiber takes over.

**Key companies:** Amphenol (APH), TE Connectivity (TEL), Credo Technology (CRDO), Belden (BDC)

---

## Layer 4: Photonics — Moving Data at the Speed of Light

Copper is great for short distances. For anything longer — between racks, between rows of servers, between buildings, between data centers — it simply doesn't scale. Signal degrades, power consumption climbs, and bandwidth caps out. That's where **photonics** enters the picture.

Photonics is the technology of moving information using light instead of electrons. An **optical transceiver** sits at the end of a fiber optic cable and handles the conversion: electrical signal in, laser light out, and vice versa on the other end. The fiber itself is glass — incredibly thin strands carrying pulses of light at (nearly) the speed of light across any distance with minimal signal loss.

As AI clusters scaled from hundreds of GPUs to tens of thousands, demand for high-speed transceivers exploded. We're currently mid-transition from **400G** (400 gigabits per second per fiber) to **800G**, with **1.6T** on the horizon. Each generation requires new transceivers, new switches, new fiber plant — a recurring capital upgrade cycle, not a one-time investment.

The supply chain here has real depth. InP substrates (AXTI) feed into component manufacturers (COHR, LITE) who produce lasers and photodetectors. Those components go into transceivers assembled by contract manufacturers (FN, AAOI). The transceivers plug into networking systems (CIEN, MRVL). Each link in that chain is seeing unprecedented demand.

We wrote about this in more depth in *The Fiber Backbone of AI*, and we'll go even deeper in a future installment of this series.

**Key companies:** Coherent (COHR), Lumentum (LITE), Fabrinet (FN), Applied Optoelectronics (AAOI), Ciena (CIEN), Marvell (MRVL)

---

## Layer 5: Cooling — The Heat Problem Nobody Told You About

This is the part that tends to surprise people: AI data centers have a heat problem unlike anything the industry has encountered before.

Traditional data centers used **air cooling** — essentially large industrial air conditioners pushing cold air through rows of servers. That works fine up to a point. But when a single rack is dissipating 120 kilowatts of heat, air physically cannot carry it away fast enough. You'd effectively need a wind tunnel blowing through each row.

The industry has been rapidly — and necessarily — migrating to **liquid cooling**. The two main approaches:

- **Direct Liquid Cooling (DLC):** Cold plates attach directly to the processor chips, and water circulates through them, absorbing heat right at the source before it spreads. This is what NVIDIA's latest DGX systems are built around.
- **Immersion Cooling:** Entire servers are submerged in a special non-conductive liquid that absorbs heat from all components at once. More complex to operate, but increasingly practical for the highest-density deployments.

Water is an extraordinarily efficient heat carrier — far better than air. But it introduces new infrastructure requirements: cooling towers, heat exchangers, plumbing, water treatment, and in dry climates, water consumption that becomes a real environmental and permitting issue. Some of the largest data centers now negotiate water rights the same way they negotiate power contracts.

**Key companies:** Vertiv (VRT — the dominant thermal management player), Modine Manufacturing (MOD), nVent Electric (NVT)

---

## Layer 6: Power — Feeding the Beast

Now we arrive at perhaps the biggest physical constraint in the entire AI buildout: **electricity**.

A hyperscale AI data center can consume hundreds of megawatts. The largest campuses being planned today are heading toward **gigawatt scale** — that's the output of a large nuclear or coal power plant, dedicated to a single data center complex. Microsoft, Google, Amazon, and Meta have collectively made commitments in the hundreds of billions of dollars, and a substantial share of that spending is simply acquiring and delivering electricity at unprecedented scale.

This creates ripple effects up and down the power chain:

**The grid itself** has to be upgraded. New transmission lines, substations, and transformers are required to move power from generation sources to data center campuses. The US electrical grid was designed decades ago and was not built for this. Waiting for a new grid connection can take **years** — it's becoming one of the primary bottlenecks slowing data center construction.

**Inside the data center**, power has to be distributed through PDUs (Power Distribution Units), transformed to the right voltages, and managed to avoid fluctuations that could damage hardware worth millions of dollars.

**The source of generation** is becoming a strategic question. Hyperscalers are signing long-term contracts directly with nuclear power plants — Microsoft famously struck a deal with Constellation Energy to restart Three Mile Island — as well as utility-scale solar and wind. The carbon commitments made by these companies aren't just PR; they're also the reason that "clean" power sources are suddenly getting premium attention from some of the largest energy buyers on earth.

**Key companies:** Vertiv (VRT), Eaton (ETN), Schneider Electric (SBGSY), Constellation Energy (CEG), Quanta Services (PWR), MYR Group (MYRG)

---

## Layer 7: Backup Power — What Happens When the Grid Fails

Behind every data center, there is a **UPS — Uninterruptible Power Supply** — that bridges the gap when grid power is interrupted. Even a fraction of a second of downtime in an AI training run can corrupt a job that took days to complete.

Traditionally, UPS systems relied on heavy **lead-acid batteries** — the same basic chemistry as a car battery, just at enormous scale. The industry is actively migrating toward **lithium-ion UPS** systems, which are lighter, faster-charging, and last through more charge cycles before needing replacement.

Some of the largest facilities are also beginning to explore using their battery banks as **grid assets** — charging during cheap off-peak hours and potentially selling power back during peak demand periods. It blurs the line between data center and power plant in a way that's still early but worth watching.

**Key companies:** EnerSys (ENS), Vertiv (VRT), Schneider Electric (SBGSY)

---

## The Big Picture

Zoom out and what you see is a supply chain that starts in a mine (copper, rare materials for compound semiconductors), runs through semiconductor fabs and photonic component factories, through data center cooling and electrical systems, all the way to a power plant and the transmission lines carrying electricity to a campus.

Every layer has a set of companies fighting for position. Every layer is constrained in ways that weren't anticipated three years ago. And every layer is seeing capital investment at a scale that is, genuinely, historic.

This is what makes the AI infrastructure story more than just an Nvidia story. The GPU is the engine. But the engine needs fuel, cooling, transmission, a chassis, and a road to drive on. All of that has to be built.

---

## What's Coming in This Series

We've done a flyover of the full stack. In upcoming parts, we'll go deeper on individual layers:

- **Part 2:** The chip in detail — GPU architecture, custom ASICs, and why TSMC controls the world
- **Part 3:** The power crisis — how AI is reshaping the US electrical grid and the companies building the new infrastructure
- **Part 4:** Cooling at scale — the race from air to liquid and what it means for the companies building thermal management
- **Part 5:** The optical layer — photonics, InP, and the fiber connecting it all

Understanding what AI actually requires — layer by layer — is the foundation for understanding where the opportunities are.

---

*This post is for informational and educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
