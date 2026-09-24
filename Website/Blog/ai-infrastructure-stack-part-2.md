# The AI Factory, Part 2: The Chip — GPUs, Custom Silicon, and the Foundry That Makes It All

*Published April 15, 2026*

---

In [Part 1](blog.html?post=ai-infrastructure-stack-part-1) we did a flyover of the full AI infrastructure stack, all seven layers from raw materials to backup power. Now we're zooming in on the layer that gets the most attention and is still the most misunderstood: the chip.

Everyone knows NVIDIA is important, but fewer people understand *why*. Why can't AMD just catch up? Why are Google, Amazon and Meta spending billions designing their own chips? And why does a single company in Taiwan have more leverage over the global economy than most countries?

Let's get into the engine room.

---

## What Makes a GPU Different

A CPU (Central Processing Unit) is the brain of a traditional computer. It's designed to handle complex tasks one at a time, very quickly. Think of it as a brilliant specialist who solves problems in sequence: fast, but always one at a time.

A GPU flips that model on its head. Instead of a few powerful cores, it packs thousands of smaller, simpler cores that all work in parallel. If the CPU is a genius at a desk, the GPU is a stadium full of people doing arithmetic at the same moment.

That's why GPUs were originally built for video games. Rendering a frame of a 3D game means calculating the color, lighting and position of millions of pixels at once. Each calculation can be simple. There just have to be millions of them happening together, and GPUs were purpose-built for exactly that.

AI training turned out to need almost the same thing. Training a neural network is, at its core, an enormous amount of matrix math: multiplying huge grids of numbers together, over and over, adjusting weights slightly each time. It's embarrassingly parallel work, exactly what a GPU was born to do.

That's the short origin story of the AI chip era. A chip designed to make video games look pretty turned out to be the perfect tool for building artificial intelligence.

---

## NVIDIA's Real Moat

NVIDIA (NVDA) saw this coming earlier than anyone, and it built an ecosystem around it that has proven incredibly hard to copy.

The hardware is the obvious starting point. The A100, H100 and now Blackwell GPUs are the gold standard for AI training and inference. Each generation brings big jumps in performance per watt, memory bandwidth and interconnect speed. Blackwell's GB200 packs 208 billion transistors and supports NVLink connections that let thousands of GPUs talk to each other at speeds no competitor can match.

That hardware is only half the story. NVIDIA's real lock-in is **CUDA**, a software platform it has been building since 2006. CUDA is the programming framework researchers and engineers use to write code that runs on NVIDIA GPUs. Twenty years of development means virtually every AI framework, every research paper and every production training pipeline is written in or optimized for CUDA. PyTorch, TensorFlow, JAX: they all run best on NVIDIA hardware because they were built on CUDA.

Leaving NVIDIA means rewriting and re-optimizing software stacks that took years to build, on top of swapping the hardware. Some companies are willing to do that work. Most aren't, especially when deadlines are tight and NVIDIA's stuff just works.

The moat is the ecosystem around the chip.

---

## AMD: The Perennial Challenger

AMD has been the "credible alternative" to NVIDIA for years now, and to its credit, it has made real progress. The MI300X is a competitive chip with more memory (192GB of HBM3) than the H100, which matters for running large models that need to keep massive weight sets in memory. Microsoft Azure and several other cloud providers offer MI300X instances, and Meta has publicly deployed AMD silicon alongside NVIDIA.

So why isn't AMD winning more?

There are two structural reasons, and CUDA is the bigger one. AMD's answer is ROCm, an open-source software stack that's improving but still lags CUDA in maturity, library support and the size of its developer community. When a researcher hits a bug in ROCm at 2am, the community and documentation just aren't as deep, and that friction compounds across thousands of engineers.

The second is interconnect. NVIDIA sells whole systems, and its GPUs are built to be wired together. NVLink and NVSwitch let NVIDIA GPUs talk to each other at bandwidths AMD's Infinity Fabric can't match at scale. For small clusters that barely matters, but for training runs using 10,000+ GPUs, the connections between chips matter as much as the chips themselves.

AMD doesn't need to beat NVIDIA outright to be a good business. It just needs to be good enough for customers who want a second source, better pricing, or specific workloads where memory capacity matters more than raw throughput. That's a real market. It's also the number two market.

---

## The Custom Silicon Wave

This is where the market really starts to fragment. The biggest buyers of AI chips looked at their NVIDIA bills, looked at their specific workloads, and decided to build their own.

**Google** was first among the hyperscalers to get into custom silicon. Its TPUs (Tensor Processing Units) have been in production since 2016, and the latest generation, Trillium (TPU v6), is designed specifically for the matrix operations that dominate AI training and inference. Google doesn't sell TPUs as standalone chips. They're available through Google Cloud, and they power Google's own products: Search, YouTube recommendations, Gemini. The logic is simple. Google runs AI at such enormous scale that even small efficiency gains per chip add up to billions of dollars saved.

**Amazon** followed with Trainium for training and Inferentia for inference. Trainium2, the latest generation, is what AWS is using to build Project Rainier, a massive cluster for Anthropic. Amazon's reasons are part cost and part supply. When NVIDIA allocation is tight, having your own chip means you're not waiting in line.

**Meta** has MTIA (Meta Training and Inference Accelerator), designed for its recommendation and ranking systems. These chips are tuned for the specific kinds of models Meta runs across Facebook, Instagram and WhatsApp, which handle billions of inference requests a day that each need to be fast and cheap.

**Microsoft** is developing Maia, its own AI accelerator, paired with a custom ARM-based CPU called Cobalt. Less is publicly known about Maia's performance, but the intent is clear: reduce dependence on any single supplier.

The pattern across all four is obvious. Every hyperscaler that can afford to is building custom silicon. They mostly aim it at the workloads where a purpose-built chip can do the job cheaper, faster or both, without necessarily trying to replace NVIDIA entirely.

---

## Broadcom and Marvell: The Arms Dealers

Most of these hyperscalers don't actually design chips from scratch in-house. They partner with semiconductor design companies that do the heavy lifting.

**Broadcom** (AVGO) is the biggest name here. It works with Google on TPU design and has publicly disclosed custom AI chip partnerships with multiple hyperscalers (widely reported to include Meta and ByteDance, among others). Broadcom's CEO has talked about a $60-90 billion addressable market for custom AI silicon. That would make it a second growth engine big enough to rival the company's entire networking division.

**Marvell** (MRVL) plays a similar role, most notably with Amazon on Trainium. It also provides the networking silicon (custom SerDes, PHYs, switching ASICs) that connects these chips inside data centers. Marvell is smaller than Broadcom but arguably more focused on the AI infrastructure opportunity.

Both companies are essentially arms dealers in the AI chip race. They build for whoever is buying, and right now everyone is buying.

---

## TSMC: The Chokepoint

Every chip we've talked about is manufactured by one company: Taiwan Semiconductor Manufacturing Company (TSM). That includes NVIDIA's GPUs, AMD's accelerators, Google's TPUs, Amazon's Trainium and Broadcom's custom designs, along with Apple's M-series and Qualcomm's Snapdragon.

TSMC doesn't design chips. Companies send it their designs, and its fabs turn them into physical silicon using processes so advanced that only two other companies on earth (Samsung and Intel) even attempt to compete, and neither is close on the most cutting-edge nodes.

TSMC manufactures over 90% of the world's most advanced chips (sub-7nm). Its 3nm and upcoming 2nm process nodes are where every major AI chip will be built for the next several years. No other foundry can produce at this density, yield and volume.

That makes TSMC the single most important company in the AI supply chain, and one of the most geopolitically significant companies on the planet. Taiwan sits 100 miles off the coast of China. Any disruption to TSMC's operations, whether from a natural disaster, geopolitical conflict or even a prolonged power outage, would halt production of virtually every advanced chip in the world.

TSMC is building fabs in Arizona and Japan to diversify, but those won't match the scale or capability of its Taiwan operations for years. The CHIPS Act in the US is providing billions in subsidies to speed up domestic production, and Intel is making a serious push with its foundry services. For now, though, the world's AI buildout runs through Hsinchu, Taiwan.

---

## The Inference Shift

One more trend matters here: the balance of AI compute is shifting from training to inference.

Training is when you build a model. It takes massive clusters running for weeks or months and consuming enormous power. Inference is when you use a model: every time you ask ChatGPT a question, every time Google ranks your search results, every time Netflix recommends a show. Each individual inference call is small, but the volume is staggering. Some estimates put inference at 80-90% of total AI compute spending within the next few years.

That shift matters because training and inference favor different chip designs. Training needs raw horsepower: the biggest, most expensive GPUs running flat out. Inference cares more about efficiency, meaning cost, power and latency per query. That's partly why custom ASICs are gaining ground. A chip designed specifically for inference on a particular kind of model can be dramatically more efficient than a general-purpose GPU doing the same job.

It's also why NVIDIA is investing so heavily in inference optimization with each new GPU generation. It knows the market is moving, and its hardware now has to win on efficiency as well as raw training performance. Blackwell was designed with this in mind, with claimed 25x inference improvements over the prior generation for certain workloads.

The companies that work out how to deliver cheap, fast, efficient inference at scale will capture an enormous share of AI spending over the next decade.

---

## The Bottom Line

The AI chip landscape is more complex than "NVIDIA wins everything." NVIDIA has a commanding lead and the deepest moat in the industry, but the market is fragmenting underneath it. AMD is a real number two, every major hyperscaler is building custom silicon, and all of it still funnels through TSMC, a single point of failure for the entire global AI supply chain.

If Part 1 was the bird's-eye view, this is your first look at the engine room. The chip is where all that infrastructure spending starts. Everything else in the stack, from the power and cooling to the networking and fiber, exists to serve what the chip demands.

Next up in [**Part 3**](blog.html?post=ai-infrastructure-stack-part-3): the power crisis. AI data centers are consuming electricity at a pace the US grid was never designed to handle. We'll look at who's building the new infrastructure, why it's taking so long, and the companies positioned to benefit.

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
