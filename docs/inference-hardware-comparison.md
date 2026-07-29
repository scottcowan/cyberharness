# Local Inference Hardware Comparison

Research compiled 2026-07-27. For a home inference server running alongside
cloud (Claude/GPT) via the cyberharness Zones routing model.

**Use case:** Haiku-tier interactive inference (3B–30B models), STT (Whisper),
embeddings, serving 6× etutor devices + 1× cyberdeck. Budget-aware cloud routing
means local box handles routine queries; cloud handles complex reasoning.

---

## Requirements

- Haiku-tier capability: fast, reliable 12B–30B inference
- OpenAI-compatible API endpoint (Ollama or vLLM)
- STT: Whisper large-v3 alongside inference models
- Concurrent devices: ~7 clients, not all simultaneous
- Expandability: multi-GPU path desirable
- Noise: tolerable (home environment, not bedroom)
- Power: not a constraint

---

## Options

### Option A — Mac Mini M4 Pro 24GB
**£1,400 | Silent | Not expandable**

| | |
|---|---|
| Memory | 24GB unified (CPU + GPU share) |
| Bandwidth | 273 GB/s |
| AI perf | ~62 TOPS (Neural Engine) |
| Max model (q4) | ~14B comfortably, 20B tight |
| Whisper large-v3 | Yes — Core ML optimised |
| Gemma 3 12B tok/s | ~50-60 tok/s |
| Noise | Silent |
| Power | 60W max |
| Expandability | None — sealed hardware |
| Ollama support | Native, first-class |

**Stack:** Gemma 3 12B (Haiku-tier), Llama 3B (Slow Zone), Whisper large-v3, nomic-embed-text.
Fits in ~16GB leaving 8GB headroom.

**Verdict:** Cleanest option. Silent, fast enough, zero configuration. CUDA-free
but llama.cpp Metal performance is excellent at this model size. Ceiling is ~20B
— no upgrade path without replacing the machine.

---

### Option B — Mac Mini M4 Pro 48GB
**£2,400 | Silent | Not expandable**

| | |
|---|---|
| Memory | 48GB unified |
| Bandwidth | 273 GB/s |
| Max model (q4) | ~34B comfortably |
| Qwen 2.5 32B tok/s | ~30-35 tok/s |
| Noise | Silent |
| Power | 60W max |
| Expandability | None |

**Stack:** Qwen 2.5 32B q4 (middle tier), Gemma 3 12B, Llama 3B, Whisper.

**Verdict:** Overkill for the stated use case given Option A handles it.
Worth it only if you want 30B+ models locally. £1,000 premium over Option A
for ~20B extra headroom.

---

### Option C — RTX 4060 16GB (existing hardware)
**£0 additional | Quiet | Limited expandability**

| | |
|---|---|
| VRAM | 16GB GDDR6 |
| Bandwidth | 272 GB/s |
| Max model (q4) | ~14B in VRAM, larger with RAM offload |
| Gemma 3 12B tok/s | ~45-55 tok/s (CUDA) |
| Noise | Near-silent at inference load |
| Power | 115W TDP |
| Expandability | Second GPU possible but no NVLink |
| Ollama support | Full CUDA |

**Already owned.** Adequate for Haiku-tier today. Second RTX 4060 can be
added for parallel model serving (no NVLink, separate models only).

**Verdict:** Best immediate option since it costs nothing. Ceiling is 14B in
VRAM without offloading. If this is sufficient, invest savings in hardware build.

---

### Option D — RTX 3090 24GB (single)
**~£750-900 used | Moderate noise | Expandable to NVLink**

| | |
|---|---|
| VRAM | 24GB GDDR6X |
| Bandwidth | 936 GB/s — 3.4× the 4060 |
| Max model (q4) | ~20B in VRAM |
| Gemma 3 12B tok/s | ~70-80 tok/s |
| Qwen 2.5 14B tok/s | ~60-70 tok/s |
| Noise | Moderate under load — audible from 2m |
| Power | 350W TDP |
| Expandability | **NVLink → 48GB combined with a second 3090** |
| Ollama/vLLM | Full CUDA |

The bandwidth jump from 4060 is the key number — 936 GB/s vs 272 GB/s means
~3× faster token generation for bandwidth-bound inference.

**Waterblock option (£874):** already fitted, runs silently in a water loop.
Without a loop it air-cools loudly under sustained load.

**Verdict:** Best single-GPU value at this price. Meaningful upgrade over 4060.
The NVLink upgrade path to 48GB is the real appeal.

---

### Option E — 2× RTX 3090 24GB NVLink ⭐ RECOMMENDED
**~£1,500-1,800 cards + £400-600 loop + £800-1,200 build = ~£2,700-3,600 total**
**Loud (air) / Silent (water) | Highly expandable**

| | |
|---|---|
| VRAM | 48GB combined (NVLink pool) |
| Bandwidth | ~1.8 TB/s combined |
| Max model q4 | ~45B comfortably |
| Max model BF16 | ~40B |
| DeepSeek R1 70B q4 tok/s | ~80-100 tok/s |
| Gemma 3 27B q4 tok/s | ~100-120 tok/s |
| Noise (air) | Loud — server room / garage level |
| Noise (water) | Silent with dual waterblocks |
| Power | ~700W GPUs, ~1,000W full system |
| Expandability | Add second 3090 later if starting with one |
| Platform | Threadripper or X299 HEDT (x16/x16 PCIe) |
| Ollama/vLLM | Full CUDA, NVLink tensor parallel |

**Build requirements:**
- Motherboard: dual x16 PCIe electrical (Threadripper Pro or X299)
- CPU: AMD Threadripper 3960X or Intel i9-X series (used, ~£200-350)
- RAM: 64GB DDR4 ECC
- PSU: 1,200-1,600W
- NVLink bridge: ~£70

**Three-tier inference stack on this machine:**
```
Slow Zone:   Llama 3.2 3B       ~2GB  — fast, Slow Zone model
Middle:      Gemma 3 27B q4     ~18GB — Haiku-tier, primary
Heavy:       70B q4 on demand   ~40GB — Sonnet-adjacent, for hard queries
STT:         Whisper large-v3   ~3GB  — always loaded
Embeddings:  nomic-embed-text   ~0.3GB
─────────────────────────────────────────────
Total:                          ~63GB — fits with headroom
```

**Staging approach:** Buy first 3090 (waterblocked, £874), run it. Add second
3090 + NVLink when ready. Water loop can be added at any point.

**Verdict:** Best price/performance for the full use case. 48GB VRAM runs 70B
comfortably — Sonnet-adjacent local capability when needed. The bandwidth
(1.8 TB/s) makes token generation genuinely fast. NVLink means the GPUs see
one unified 48GB pool, not two separate 24GB pools.

---

### Option F — Intel Arc Pro B60 ×4 (96GB)
**~£3,200-4,000 cards + server platform = ~£4,500-6,000 total**
**Very loud | Expandable within Intel ecosystem**

| | |
|---|---|
| VRAM | 96GB GDDR6 (4× 24GB) |
| Bandwidth | 4× 456 GB/s = ~1.8 TB/s total |
| Max model BF16 | 70B+ comfortably |
| DeepSeek 132B MoE tok/s | 289 tok/s sustained (measured) |
| Noise | Very loud — server grade |
| Power | ~940W peak |
| Expandability | Intel LLM Scaler stack only |
| Ollama/vLLM | Via Intel fork — behind mainline by ~1 month |

**Measured benchmark (StorageReview, 4× B60, DeepSeek R1 132B BF16, concurrency 64):**
- 289 tok/s sustained generation
- 574 tok/s peak
- 1,425 tok/s prompt processing

**Caveat:** Software stack friction. Intel LLM Scaler is ~1 month behind mainline
vLLM. Newer models (Qwen 3.5, GLM Flash 4.7) may not load. MoE instability
under high concurrency observed. Not Ollama-compatible natively.

**Verdict:** Right call only if you specifically need 70B+ BF16 precision at
this budget. For Haiku-tier use case it's 3× the cost of Option E for marginal
practical benefit given the software immaturity.

---

### Option G — Tiiny AI Pocket Lab
**$1,399-1,999 (~£1,100-1,600) | Silent | Not expandable**

| | |
|---|---|
| Addressable memory | 80GB (32GB SoC + 48GB NPU — split pools) |
| Bridge bandwidth | ~6-7 GB/s PCIe Gen4 x4 |
| 120B MoE tok/s | ~4.5 tok/s at 64K context |
| Time to first token (64K) | **28 minutes** |
| Noise | Silent |
| Power | 30W |
| Form factor | USB-C peripheral — requires host PC |
| Ollama support | Via TiinySDK only |

**The "80GB" is misleading** — it is two separate pools with a slow bridge.
Models spanning both pools suffer catastrophically. Models ≤20B that fit in
one pool (~48GB dNPU) perform much better (~362 tok/s prefill).

**For RAG and agent loops:** 28-minute TTFT at 64K context makes it
impractical. The cyberharness use case relies on fast multi-turn exchanges.

**Verdict:** Not recommended for this use case. An RTX 4060 (already owned)
outperforms it on practical benchmarks at zero additional cost.

---

### Option H — Ryzen AI Max Mini PC (128GB unified)
**~£1,700-1,800 | Silent | Not expandable**

| | |
|---|---|
| Memory | 128GB unified LPDDR5X |
| Bandwidth | ~273 GB/s |
| NPU | 50 TOPS Ryzen AI |
| Max model | 70B q4 comfortably |
| 70B q4 tok/s | ~15-20 tok/s (bandwidth-bound) |
| Noise | Near-silent |
| Power | ~65W |
| Expandability | None — integrated |
| Ollama support | Full (CPU + GPU path) |

**The 128GB is genuinely unified** — unlike Tiiny, no PCIe bridge penalty.
Can load 70B full precision. Bandwidth is the ceiling: at 273 GB/s, a 70B
model produces ~15-20 tok/s — acceptable but not fast.

**Verdict:** Better than Tiiny at the same price. Good if silence and a single
compact device matter more than raw speed. Not a recommendation over Option E
if you want expandability and CUDA performance.

---

### Option I — NVIDIA DGX Station (GB10 Grace Blackwell)
**~£2,000-2,800 est. | Quiet desktop | Expandable via NVLink to second unit**
**Status: Not yet released — expected 2026**

| | |
|---|---|
| Memory | 128GB unified (NVLink-C2C — genuinely unified, no split-pool penalty) |
| Bandwidth | ~4 TB/s |
| AI performance | ~1,000 TOPS |
| Architecture | Blackwell — best INT4/FP8 inference efficiency |
| Max model BF16 | 70B comfortably, 120B+ with two units |
| 70B q4 tok/s | ~200+ (estimated) |
| 70B BF16 tok/s | ~100+ (estimated) |
| Noise | Quiet desktop fan — not silent but not loud |
| Power | ~300W |
| Expandability | Second GB10 unit via NVLink → 256GB combined |
| Ollama/vLLM | Full CUDA (Blackwell) |

**Why it's compelling:** 128GB genuinely unified memory at ~4 TB/s bandwidth
is the key number. No split-pool penalty (unlike Tiiny), no NVLink bridge
latency (unlike multi-GPU builds). A single unit runs 70B BF16 without
quantisation — Sonnet-adjacent quality with no compromises.

**Why to be cautious:**
- Not released as of 2026-07-28 — no confirmed UK price or ship date
- NVIDIA consumer launches regularly slip
- Price estimate based on DGX Spark ($3,999) positioning — if it lands
  above ~£2,500 the value proposition weakens vs. the 2× 3090 build
- Limited software availability for Blackwell on day one (drivers, Ollama
  support, vLLM optimisation typically lags 1-3 months)

**The case for waiting:** If it launches at £2,000-2,500, it beats the 2× 3090
NVLink build on every metric — faster, more memory, quieter, no build complexity.
**The case against waiting:** Could be 6-12 months away. The 3090 build works
today, holds resale value, and can be sold when the Station ships.

**Verdict:** Best option *if* it launches at the expected price. Monitor the
announcement — if UK pricing lands ≤£2,500 it becomes the clear recommendation
over Option E. If it prices above £3,000 the 2× 3090 build remains better value.

---

## Comparison Summary

| Option | Cost | VRAM | Best model | tok/s (30B q4) | Noise | Expandable |
|---|---|---|---|---|---|---|
| A — Mac Mini 24GB | £1,400 | 24GB unified | 14B | ~55 | Silent | No |
| B — Mac Mini 48GB | £2,400 | 48GB unified | 34B | ~35 | Silent | No |
| C — RTX 4060 16GB | £0 | 16GB | 14B | ~50 | Quiet | Limited |
| D — RTX 3090 24GB | £750-900 | 24GB | 20B | ~75 | Moderate/Silent* | Yes → NVLink |
| **E — 2× RTX 3090 NVLink** | **£2,700-3,600** | **48GB** | **45B q4 / 70B q4** | **~110** | **Loud/Silent*** | **Yes** |
| F — 4× Arc Pro B60 | £4,500-6,000 | 96GB | 132B BF16 | ~200 | Very loud | Intel only |
| G — Tiiny AI | £1,100-1,600 | 80GB* | 20B (practical) | ~17 | Silent | No |
| H — Ryzen AI Max | £1,700-1,800 | 128GB unified | 70B | ~18 | Near-silent | No |
| **I — DGX Station GB10** | **~£2,000-2,800 est.** | **128GB unified** | **70B BF16** | **~200+** | **Quiet** | **Yes (NVLink ×2)** |

*Water-cooled 3090 = silent. Air-cooled = loud.
*Tiiny 80GB is split-pool — practical ceiling is ~20B.
†DGX Station not yet released — price estimated, specs from NVIDIA announcements.

---

## Recommendation

### Best overall price/performance: Option E — 2× RTX 3090 24GB NVLink

**Why:**
1. **48GB NVLink pool** at 1.8 TB/s — runs 70B q4 at ~80-100 tok/s. Nothing
   else at this price delivers this combination.
2. **CUDA ecosystem** — Ollama, vLLM, faster-whisper, llama.cpp all first-class.
   No software stack friction.
3. **Three-tier model stack** fits in VRAM — 3B Slow Zone + 27B Haiku + 70B
   Sonnet-adjacent + Whisper, all loaded simultaneously.
4. **Expandable** — start with one 3090 (Option D), add second + NVLink later.
5. **Noise solved by water cooling** — dual waterblocks + loop = silent.
   Both 3090s can be watercooled: one already has a block (£874 listing).

**Staged path:**
1. Buy waterblocked 3090 (£874) — run it, validate the stack
2. Buy second 3090 (~£700) + NVLink bridge (£70)
3. Add water loop for second card (~£300-400) when budget allows

**Platform:** Threadripper 3960X or X299 board for true x16/x16.
Full build ~£2,700-3,600 depending on platform and cooling choices.

---

### Best if you want silent and simple: Option A — Mac Mini M4 Pro 24GB (£1,400)

Handles the Haiku-tier use case cleanly. Gemma 3 12B at 50-60 tok/s is fast
enough for all 7 devices. Zero noise, minimal setup, Ollama native. Ceiling
is ~20B but that covers everything except the Sonnet-adjacent tier.

---

### Best if you can wait: Option I — DGX Station GB10 (~£2,000-2,800 est.)

128GB genuinely unified at 4 TB/s, quiet, single device, expandable to 256GB.
Beats Option E on every metric if it lands at the expected price. Monitor the
UK launch announcement. Decision point: ≤£2,500 → buy the Station.
\>£3,000 → buy Option E instead.

---

### Best immediate action (no spend): Option C — Use existing RTX 4060

Install Ollama, pull Gemma 3 12B, serve the API. Validate the full cyberharness
stack works before spending anything. Upgrade to Option D, E, or I when the
workflow is proven and pricing is confirmed.

---

## Cost Model: Local Hardware vs Cloud

### Current cloud pricing (2026)

| Model tier | Provider | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|---|
| Haiku-equivalent | Claude Haiku 4.5 | $0.80 | $4.00 |
| Sonnet-equivalent | Claude Sonnet 5 | $3.00 | $15.00 |
| GPT-4o mini | OpenAI | $0.15 | $0.60 |
| Whisper STT | OpenAI | $0.006/min | — |

### Estimated usage — 6 etutor devices + cyberdeck

| Source | Daily tokens |
|---|---|
| 6 children × 2 sessions × 20 exchanges × 500 tokens | ~120,000 |
| Cyberdeck voice queries + discuss phases | ~20,000 |
| Whisper STT (~60 min/day across all devices) | — |
| **Total** | **~140,000 tokens/day = ~51M tokens/year** |

**Annual cloud cost at current usage:**

| Routing | Annual cost |
|---|---|
| All Haiku (~$2.40/1M blended) | ~$122 (~£96) |
| All Sonnet (~$9/1M blended) | ~$459 (~£360) |
| Cyberharness mixed (80% Haiku / 20% Sonnet) | ~$190 (~£150) |
| Whisper STT (60 min/day × 365) | ~$131 (~£103) |
| **Realistic total (mixed + STT)** | **~£250/year** |

### Breakeven analysis

Hardware pays for itself when cumulative cloud savings equal the hardware cost.

| Hardware | Cost | Annual electricity | Annual saving vs cloud | Breakeven |
|---|---|---|---|---|
| RTX 4060 (owned) | £0 | ~£80 | £170 | Immediate |
| Single RTX 3090 | £800 | ~£120 | £130 | ~6 years |
| 2× RTX 3090 NVLink | £2,700-3,600 | ~£180 | £70 | Never at current usage |
| DGX Station | ~£2,200 | ~£100 | £150 | ~15 years |
| Mac Mini M4 Pro 24GB | £1,400 | ~£50 | £200 | ~7 years |

**At current usage levels, cloud wins on pure economics.** Hardware only
breaks even if usage scales significantly.

### The scaling inflection points

| Daily token usage | Annual cloud cost (mixed) | Hardware payback period (3090 NVLink) |
|---|---|---|
| 140K (current estimate) | ~£250 | Never |
| 500K (3.5× — more sessions, longer) | ~£900 | ~4 years |
| 1M (7× — full use, agents, cyberharness) | ~£1,800 | ~2 years |
| 2M (14× — production scale) | ~£3,600 | ~1 year |

**Inflection point for the 3090 build: ~700K tokens/day.** Below that, cloud
is cheaper. Above that, hardware pays off within 3 years.

### The inflation scenario

Cloud AI pricing has deflated ~95% over 2023-2026 for commodity tiers.
This deflationary trend may not continue if:
- Frontier model quality diverges further from open-weight models
- Regulatory compliance costs for children's data processing increase
- The commodity inference market consolidates

If cloud prices inflate 5× from current levels:

| Daily tokens | Annual cloud cost (5× inflation) | Hardware payback |
|---|---|---|
| 140K | ~£1,250 | ~2.5 years (3090 build) |
| 500K | ~£4,500 | ~9 months |

A 5× inflation scenario makes hardware investment clearly justified even
at current modest usage.

### The non-financial arguments for local

These do not appear in a cost model but are real:

**Privacy.** Children's educational sessions — questions asked, concepts
struggled with, interests revealed, neurodivergence flags — are intimate
cognitive data. Sending this to Anthropic or OpenAI servers is a meaningful
privacy tradeoff regardless of their policies. Local inference means none
of this leaves the house.

**Offline sovereignty (Slow Zone model).** The cyberharness is designed to
operate locally when the Beyond is unavailable. Cloud dependency breaks this
design. A rate limit or outage during a child's session is a worse failure
mode than slightly slower local inference.

**Latency.** Cloud round-trips add 200-800ms per exchange depending on
provider and network. For voice-based etutor sessions (speak → transcribe →
respond → TTS), this compounds noticeably. Local inference is <50ms.

**No per-token ceiling.** Socratic tutoring benefits from verbose, patient
responses. Cloud inference creates implicit pressure to keep prompts short
and sessions cheap. Local inference removes that pressure entirely.

**Regulatory trajectory.** GDPR Article 8, COPPA, and emerging EU AI Act
provisions create increasing compliance complexity for processing children's
data via third-party cloud providers. Local inference sidesteps this entirely
and is likely to become a stronger argument over time, not weaker.

### Recommended approach

1. **Now:** Use existing RTX 4060 + cloud routing via cyberharness.
   Measure actual token usage for 4-6 weeks.

2. **Review:** If monthly cloud bill is under £30 and privacy/offline
   concerns are acceptable → cloud routing is fine indefinitely.

3. **Upgrade trigger:** Monthly cloud bill exceeds £100, OR privacy
   concerns harden, OR DGX Station launches at ≤£2,500.

4. **Hardware choice at upgrade:** Follow the recommendation matrix above.
   DGX Station if available and ≤£2,500. 2× RTX 3090 NVLink otherwise.
