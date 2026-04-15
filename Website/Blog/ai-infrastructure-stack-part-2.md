# The AI Factory, Part 2: The Chip — GPUs, Custom Silicon, and the Foundry That Makes It All

*Published April 15, 2026*

---

In Part 1 we did a flyover of the full AI infrastructure stack, all seven layers from raw materials to backup power. Now we're zooming in on the layer that gets the most attention and is still the most misunderstood: the chip.

Everyone knows NVIDIA is important. Fewer people understand *why*. Why can't AMD just catch up? Why are Google, Amazon, and Meta spending billions designing their own chips? And why does a single company in Taiwan have more leverage over the global economy than most countries?

Let's get into it.

---

## What Makes a GPU Different

A CPU (Central Processing Unit) is the brain of a traditional computer. It's designed to handle complex tasks one at a time, very quickly. Think of it as a brilliant specialist who solves problems sequentially, fast, but always one at a time.

A GPU flips that model. Instead of a few powerful cores, a GPU packs thousands of smaller, simpler cores that all work in parallel. It's less like a single genius and more like a stadium full of people doing math simultaneously.

This is why GPUs were originally built for video games. Rendering a frame of a 3D game means calculating the color, lighting, and position of millions of pixels at once. You don't need each calculation to be complicated. You need millions of simple calculations done at the same time. GPUs were purpose-built for exactly that.

AI training turned out to need almost the same thing. Training a neural network is, at its core, an enormous amount of matrix math: multiplying huge grids of numbers together, over and over, adjusting weights slightly each time. It's embarrassingly parallel work. The kind of thing a GPU was born to do.

That's the origin story. A chip designed to make video games look pretty turned out to be the perfect tool for building artificial intelligence.

---

## NVIDIA's Real Moat

NVIDIA (NVDA) didn't just get lucky. They saw this coming earlier than anyone and built an ecosystem around it that's proven incredibly difficult to replicate.

The hardware matters, obviously. The A100, H100, and now Blackwell GPUs are the gold standard for AI training and inference. Each generation brings significant jumps in performance per watt, memory bandwidth, and interconnect speed. Blackwell's GB200 packs 208 billion transistors and supports NVLink connections that let thousands of GPUs talk to each other at speeds no competitor can match.

But the hardware is only half the story. NVIDIA's real lock-in is **CUDA**, a software platform they've been building since 2006. CUDA is the programming framework that researchers and engineers use to write code that runs on NVIDIA GPUs. Twenty years of development means that virtually every AI framework, every research paper, every production training pipeline is written in or optimized for CUDA. PyTorch, TensorFlow, JAX: they all run best on NVIDIA hardware because they were built on CUDA.

Switching away from NVIDIA isn't just a hardware swap. It means rewriting and re-optimizing software stacks that took years to develop. Some companies are willing to do that work. Most aren't, especially when deadlines are tight and NVIDIA's stuff just works.

That's a moat. Not the chip itself, but the ecosystem around it.

---

## AMD: The Perennial Challenger

AMD has been the "credible alternative" to NVIDIA for years now, and to their credit, they've made real progress. The MI300X is a competitive chip. It has more memory (192GB of HBM3) than the H100, which matters for running large models that need to keep massive weight sets in memory. Microsoft Azure and several cloud providers offer MI300X instances. Meta has publicly deployed AMD silicon alongside NVIDIA.

So why isn't AMD winning more?

Two reasons. First, CUDA. AMD's answer is ROCm, an open-source software stack that's improving but still lags behind CUDA in maturity, library support, and the size of its developer community. When a researcher hits a bug in ROCm at 2am, the community and documentation just aren't as deep. That friction compounds across thousands of engineers.

Second, interconnect. NVIDIA doesn't just sell GPUs. It sells systems. NVLink and NVSwitch let NVIDIA GPUs communicate with each other at bandwidths that AMD's Infinity Fabric can't match at scale. For small clusters this doesn't matter much. For training runs using 10,000+ GPUs, the interconnect between chips matters as much as the chips themselves.

AMD doesn't need to beat NVIDIA outright to be a good business. They just need to be good enough for the customers who want a second source, better pricing, or specific workloads where memory capacity matters more than raw throughput. That's a real market. But it's the number two market.

---

## The Custom Silicon Wave

Here's where things get really interesting. The biggest buyers of AI chips looked at their bills from NVIDIA, looked at their specific workloads, and decided to build their own.

**Google** was first. Their TPUs (Tensor Processing Units) have been in production since 2016. The latest generation, Trillium (TPU v6), is designed specifically for the matrix operations that dominate AI training and inference. Google doesn't sell TPUs as standalone chips. They're available through Google Cloud, and they power Google's own products: Search, YouTube recommendations, Gemini. Google's rationale is straightforward. They run AI at such enormous scale that even small efficiency gains per chip translate into billions of dollars saved.

**Amazon** followed with Trainium for training and Inferentia for inference. Trainium2, the latest generation, is what AWS is using to build Project Rainier, a massive cluster for Anthropic. Amazon's motivation is partly cost, partly supply. When NVIDIA allocation is tight, having your own chip means you're not waiting in line.

**Meta** has MTIA (Meta Training and Inference Accelerator), designed for their recommendation and ranking systems. These aren't general-purpose AI chips. They're tuned for the specific types of models Meta runs across Facebook, Instagram, and WhatsApp. Billions of inference requests per day, each one needing to be fast and cheap.

**Microsoft** is developing Maia, its own AI accelerator, paired with a custom ARM-based CPU called Cobalt. Less is publicly known about Maia's performance, but the intent is clear: reduce dependency on any single supplier.

The pattern is obvious. Every hyperscaler that can afford to is building custom silicon. Not necessarily to replace NVIDIA entirely, but to handle the workloads where a purpose-built chip can do the job cheaper, faster, or both.

---

## Broadcom and Marvell: The Arms Dealers

Most of these hyperscalers don't actually design chips from scratch in-house. They partner with semiconductor design companies who do the heavy lifting.

**Broadcom** (AVGO) is the biggest name here. They work with Google on TPU design and have publicly disclosed custom AI chip partnerships with multiple hyperscalers (widely reported to include Meta and ByteDance, among others). Broadcom's CEO has talked about a $60-90 billion addressable market for custom AI silicon. That's not a side business. That's a potential second growth engine rivaling their entire networking division.

**Marvell** (MRVL) plays a similar role, most notably with Amazon on Trainium. They also provide the networking silicon (custom SerDes, PHYs, switching ASICs) that connects these chips together inside data centers. Marvell is smaller than Broadcom but arguably more focused on the AI infrastructure opportunity.

Both companies are essentially arms dealers in the AI chip race. They don't pick winners. They build for whoever is buying. And right now, everyone is buying.

---

## TSMC: The Chokepoint

Every chip we've talked about, NVIDIA's GPUs, AMD's accelerators, Google's TPUs, Amazon's Trainium, Broadcom's custom designs, Apple's M-series, Qualcomm's Snapdragon, all of them are manufactured by one company: Taiwan Semiconductor Manufacturing Company (TSM).

TSMC doesn't design chips. It fabricates them. Companies send TSMC their chip designs, and TSMC's fabs turn those designs into physical silicon using manufacturing processes so advanced that only two other companies on earth (Samsung and Intel) even attempt to compete. And neither is close on the most cutting-edge nodes.

The numbers are hard to overstate. TSMC manufactures over 90% of the world's most advanced chips (sub-7nm). Their 3nm and upcoming 2nm process nodes are where every major AI chip will be built for the next several years. No other foundry can produce at this density, yield, and volume.

This makes TSMC the single most important company in the AI supply chain. It also makes it one of the most geopolitically significant companies on the planet. Taiwan sits 100 miles off the coast of China. Any disruption to TSMC's operations, whether from natural disaster, geopolitical conflict, or even just a prolonged power outage, would halt the production of virtually every advanced chip in the world.

TSMC is building fabs in Arizona and Japan to diversify, but these facilities won't match the scale or capability of the Taiwan operations for years. The CHIPS Act in the US is providing billions in subsidies to accelerate domestic production, and Intel is making a serious push with its foundry services. But the reality today is that the world's AI buildout runs through Hsinchu, Taiwan.

---

## The Inference Shift

One more trend worth understanding: the balance of AI compute is shifting from training to inference.

Training is when you build a model. It requires massive clusters running for weeks or months, consuming enormous power. Inference is when you use a model: every time you ask ChatGPT a question, every time Google ranks your search results, every time Netflix recommends a show. Each individual inference call is small, but the volume is staggering. Some estimates put inference at 80-90% of total AI compute spending within the next few years.

This shift matters because training and inference favor different chip architectures. Training needs raw horsepower: the biggest, most expensive GPUs running at full power. Inference cares more about efficiency: cost per query, power per query, latency per query. This is partly why custom ASICs are gaining ground. A chip designed specifically for inference on a particular model type can be dramatically more efficient than a general-purpose GPU doing the same job.

It's also why NVIDIA is investing so heavily in inference optimization with each new GPU generation. They know the market is moving, and they need their hardware to win on efficiency, not just raw training performance. Blackwell's architecture was designed with this in mind, with claimed 25x inference improvements over the prior generation for certain workloads.

The companies that figure out how to deliver cheap, fast, efficient inference at scale will capture an enormous share of AI spending over the next decade.

---

## The Bottom Line

The AI chip landscape is more complex than "NVIDIA wins everything." NVIDIA has a commanding lead and the deepest moat in the industry, but the market is fragmenting. AMD is a real number two. Every major hyperscaler is building custom silicon. And all of it funnels through TSMC, a single point of failure for the entire global AI supply chain.

If Part 1 was the bird's-eye view, this is your first look at the engine room. The chip is where all that infrastructure spending starts. Everything else in the stack, the power, the cooling, the networking, the fiber, exists to serve what the chip demands.

Next up in **Part 3**: the power crisis. AI data centers are consuming electricity at a pace the US grid was never designed to handle. We'll look at who's building the new infrastructure, why it's taking so long, and the companies positioned to benefit.

---

**Key companies mentioned in this post:**

| Company | Ticker | Role |
|---------|--------|------|
| NVIDIA | NVDA | GPU design, CUDA ecosystem, AI systems |
| AMD | AMD | GPU design (MI300X), ROCm software |
| Broadcom | AVGO | Custom ASIC design for hyperscalers |
| Marvell | MRVL | Custom ASIC design, networking silicon |
| TSMC | TSM | Foundry (fabricates nearly all advanced chips) |
| Google | GOOG | TPUs (custom AI training/inference chips) |
| Amazon | AMZN | Trainium/Inferentia (custom AI chips via AWS) |
| Meta | META | MTIA (custom training/inference accelerator) |
| Microsoft | MSFT | Maia AI accelerator, Cobalt CPU |
| Intel | INTC | Foundry services, Gaudi AI accelerators |

---

*This post is for informational and educational purposes only and does not constitute financial advice. Always do your own research before making investment decisions.*
