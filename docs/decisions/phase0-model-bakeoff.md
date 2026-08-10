# Phase 0 — model bake-off

**Date:** 2026-08-06
**Task:** build-plan Phase 0, "Quick model bake-off: 2-3 candidate small models, a handful of hand-written matchup questions, scored by hand."
**Status:** Decided — **Qwen/Qwen3-4B-Instruct-2507**

Every output below was actually generated on this machine in a single run. Nothing here is illustrative or reconstructed.

## Setup

| | |
|---|---|
| Hardware | Apple Silicon Mac (arm64), no CUDA. `torch.cuda.is_available()` is `False`. |
| Backend | MPS (`torch.backends.mps.is_available()` → `True`), `dtype=torch.bfloat16` |
| Stack | `torch` 2.11.0, `transformers` 5.3.0 |
| Generation | `max_new_tokens=300`, `do_sample=False` (greedy), no other sampling overrides |
| Prompting | Chat template per model, one system prompt (below), zero-shot, no retrieval, no few-shot examples |
| Wall clock | **12m 57s total** for all 3 models × 5 questions, including ~7m 40s of first-time weight download |

System prompt used for all 15 generations:

> You are a League of Legends coach. Give concise, rank-aware matchup advice for the game phase asked about. If you do not have reliable data for this matchup at this rank, say so plainly instead of inventing specifics.

That last sentence is deliberate: Q5 is the abstention probe, and a model that can't take an explicit instruction to abstain won't abstain after fine-tuning either.

**Repo IDs** (verified on huggingface.co, not guessed):

| Requested | Actual repo | Note |
|---|---|---|
| Qwen3-1.7B-Instruct | `Qwen/Qwen3-1.7B` | No `-Instruct` suffix exists. `Qwen/Qwen3-1.7B` *is* the instruct-tuned hybrid model (`-Base` is the raw one). Run with `enable_thinking=False` so it answers instead of emitting a reasoning block. |
| Qwen3-4B-Instruct | `Qwen/Qwen3-4B-Instruct-2507` | Non-thinking instruct refresh. `Qwen/Qwen3-4B` is the older hybrid. |
| Phi-4-mini-instruct | `microsoft/Phi-4-mini-instruct` | Exact match. |

## The 5 questions

1. Darius vs. Yasuo, top lane, Diamond — early game trade pattern?
2. Kai'Sa vs. Miss Fortune, bot lane, Gold — late game teamfight positioning?
3. Lee Sin vs. Kayn, jungle, Platinum — mid game pathing and objective priority?
4. Azir vs. Yone, mid lane, Bronze — early game lane strategy?
5. Aphelios vs. Zeri, bot lane, Iron — early game? *(deliberately thin-data — an honest low-confidence answer scores higher than a confident fabricated one)*

## Raw model outputs

Verbatim, unedited. Truncation mid-sentence means the 300-token cap was hit.

### Qwen/Qwen3-1.7B

Load (download excluded from per-question timing): 102.2s, device `mps`.

#### Q1 — 9.3s, 169 new tokens

```
In the early game, Darius and Yasuo often engage in a back-and-forth trade, especially in the Diamond tier. The key patterns include:

- **Early aggression**: Both players will often push early, using their burst and mobility to secure kills.
- **Trade mechanics**: They tend to trade for kills, often using a "push and kill" or "push and die" strategy.
- **Yasuo's pressure**: Yasuo's high mobility and burst make him a threat to Darius, especially in the early game.
- **Darius' counterplay**: Darius can often counter Yasuo's pressure with his sustain and crowd control.

**Note**: At this rank, data is limited, so the advice is based on general patterns observed in the early game. Adjust based on specific team dynamics and game flow.
```

#### Q2 — 15.1s, 300 new tokens

```
In late game teamfights, **Kai'Sa** and **Miss Fortune** are both high-risk, high-reward champions with strong teamfight roles. Here's a concise matchup analysis for **bot lane, Gold rank**:

### **Kai'Sa** (Tank, Crowd Control, Crowd Control)
- **Role**: Supports and tank, often used as a "tanky" support.
- **Strengths**: High survivability, strong crowd control, can control the battlefield.
- **Weaknesses**: Can be overpowered if not positioned well, may not be as effective in late game if not supported.

### **Miss Fortune** (Support, Crowd Control, Crowd Control)
- **Role**: Supports and damage dealer, often used as a "damage" support.
- **Strengths**: High damage output, strong crowd control, can control the battlefield.
- **Weaknesses**: Can be overpowered if not positioned well, may not be as effective in late game if not supported.

### **Late Game Teamfight Positioning Tips**:
- **Kai'Sa** should be positioned **behind** the team to absorb damage and control the front line.
- **Miss Fortune** should be positioned **front** to deal damage and control the battlefield.
- Both should be **close to the front** to maximize their damage and crowd control.

### **Conclusion**:
In late game, **Kai'Sa** and **Miss Fortune** are both strong
```

#### Q3 — 14.7s, 300 new tokens

```
Lee Sin and Kayn are both strong champions in the Platinum rank, but their matchup is generally balanced. Here's a concise breakdown of their **mid-game pathing and objective priority**:

### **Pathing:**
- **Lee Sin** tends to focus on **clearing lanes** and **securing kills** in the mid lane, often using his **Rapid Reckoning** and **Lee Sin's Strike** to pressure the enemy team.
- **Kayn** is more of a **support** and **clearer** champion, often focusing on **clearing lanes** and **pushing the enemy team back**. He is known for his **Rapid Reckoning** and **Kayn's Strike**.

### **Objective Priority:**
- **Lee Sin** prioritizes **clearing lanes** and **securing kills** in the mid lane, often focusing on **neutral towers** and **map control**.
- **Kayn** is more focused on **clearing lanes** and **pushing the enemy team back**, with a strong focus on **neutral towers** and **map control**.

### **Conclusion:**
- In the **Platinum rank**, both champions are **strong and balanced**, but **Lee Sin** is slightly more **aggressive** and **focused on kills**, while **Kayn** is more **supportive** and **focused on clear lanes**.
- **Pathing** is generally **neutral**, but **Lee
```

#### Q4 — 10.3s, 216 new tokens

```
In the early game, when playing Azir vs. Yone in a Bronze rank, the key is to focus on **avoiding early aggression** and **maintaining lane control**. Here's a concise strategy:

- **Avoid early aggressive plays**: Yone is a strong mid laner with good burst and mobility, so avoid getting caught in early fights.
- **Stay in lane**: Keep your distance from Yone to avoid being targeted, and use your abilities to push the lane if possible.
- **Use your abilities to control the map**: Azir can use his **E (Rapid Strike)** to clear waves and set up for kills, while Yone can use her **Q (Rapid Strike)** and **W (Rapid Strike)** to engage and deal damage.
- **Be patient**: Don’t rush into fights early; focus on farming and maintaining a safe position.

If you're at a lower rank, this strategy is still applicable, but you’ll need to be more cautious and focus on **farm and vision control** to stay safe.
```

#### Q5 — 9.4s, 188 new tokens

```
In the early game, Aphelios and Zeri are a strong matchup, especially in a bot lane with an Iron (low-tier) support. Here's a concise breakdown:

- **Aphelios** has strong early-game burst and can pressure Zeri effectively, especially with his **Rage of the Destroyer** and **Aphelios' Ultimate**.
- **Zeri** is a high-risk, high-reward pick, but she can be vulnerable in the early game if not supported well.
- **Iron** (low-tier support) can help with early game pressure and farm, but may not be enough to counter Zeri's early aggression.

**Recommendation:** Use **Aphelios' early game burst** to pressure Zeri, and **support Zeri with a strong carry** if possible. If Iron is too weak, consider rotating to a better support or using a different lane.
```

### Qwen/Qwen3-4B-Instruct-2507

Load (download excluded from per-question timing): 201.1s, device `mps`.

#### Q1 — 37.4s, 300 new tokens

```
At Diamond rank, Darius vs. Yasuo in the top lane typically features a **highly aggressive early game trade pattern** due to their similar early-game engagement styles and lane control.

**Early Game Trade Pattern (Diamond):**

- **Darius** starts with strong early pressure due to his **high mobility and burst damage** (especially with his Q, W, and E). He often **pushes the lane aggressively** to force Yasuo into a trade or to deny vision.
- **Yasuo**, with his **high mobility and burst**, can **counter with quick trades** using his Q (Sword of the Wind) and E (Sword of the Wind) to close distance and apply pressure.
- **Common early trade flow**:  
  Darius uses his W (Sword of the Wind) to initiate, then follows up with E (Sword of the Wind) to close range. Yasuo responds with Q to dodge or counter, then uses E to reposition or escape.  
  If Yasuo lands a good Q or E, he can **disengage or pressure Darius’s backline**.
- **Darius often tries to force a 1v1** in the early game, especially with his **high damage and ability to kite**. However, Yasuo’s mobility allows him to **avoid the trade** and instead **focus on farming or pushing**.

**Key Insight (Diamond):**  
At this rank, **D
```

#### Q2 — 32.8s, 300 new tokens

```
At the **late game**, in a **Kai'Sa vs. Miss Fortune** bot lane matchup, **teamfight positioning** is critical due to their distinct playstyles and abilities.

### Kai'Sa (Flex/Support) vs. Miss Fortune (Damage Carry):
- **Kai'Sa** has strong burst and mobility, but relies on positioning to maximize her **E (Sprint)** and **Q (Sprint)** for repositioning and escape.
- **Miss Fortune** excels in burst damage and mobility with **Q (Rapid Fire)** and **E (Rapid Fire)**, but is vulnerable to crowd control and positioning.

### Late Game Teamfight Positioning Tips:
1. **Kai'Sa should stay back and support the team** — avoid being the first to engage. Use her **E** to reposition or escape if the fight turns against her.
2. **Miss Fortune should stay in the front line** — she can take damage to apply pressure, but **don’t go first** unless the enemy team is low on health or lacks crowd control.
3. **Avoid direct 1v1s** — both champions are vulnerable to CC and burst. If the enemy has a strong CC (like a **Soraka** or **Zed**), let Miss Fortune take the hit and use her **Q** to reposition.
4. **Kai'Sa should use her ultimate (Sprint)** to reposition or
```

#### Q3 — 34.0s, 300 new tokens

```
At Platinum rank, **Lee Sin vs. Kayn in the jungle** presents a high-risk, high-reward matchup due to their aggressive, mobility-driven playstyles. In **mid-game pathing and objective priority**, here’s the rank-aware advice:

### Objective Priority:
- **First Blood / Early Lane Pressure**:  
  Kayn has strong early game pressure with his **Q (Soul of the Storm)** and **E (Soul of the Storm)**, especially in the jungle. He can close gaps and initiate with **W (Soul of the Storm)** and **E**.  
  Lee Sin, while strong in 1v1, is less effective early due to his **long cooldowns** and **poor early mobility**.  
  → **Priority: Don’t let Kayn get first blood**. Focus on **controlling the jungle** and **avoiding early engagements**.

- **Dragon & Baron**:  
  Both champions have strong late-game potential, but **Kayn’s ability to farm and pressure mid-lane** makes him a threat to **baron**.  
  → **Baron is a priority** if you can control the jungle and avoid being caught in a 3v3.  
  → **Dragon (especially Rift Herald)** is secondary unless Kayn is pushing aggressively.

- **Inhibitors & Turrets**:  
  Kayn can **push lanes aggressively** and **use his E to reposition**
```

#### Q4 — 34.6s, 300 new tokens

```
At Bronze rank, Azir vs. Yone in mid lane early game:

**Azir (as the mid laner):**  
Azir is a strong early-game presence with his ability to zone and pressure with his ultimate (Soul of the Storm). However, he lacks early mobility and has limited burst damage.  

**Yone (as the mid laner):**  
Yone has strong early game aggression, good mobility, and can pressure with her Q (Sprint) and E (Riposte). She can easily chase or escape, and her early game is very active.

**Early Game Lane Strategy (Azir vs. Yone):**  
- **Avoid early fights** — Yone is aggressive and can easily outmaneuver Azir in a 1v1.  
- **Focus on farming** — Let Yone push and farm first. Azir should stay in the back, farm safely, and avoid engaging unless Yone is out of position.  
- **Use vision control** — Place a vision (like a tower or bush) to prevent Yone from ganking or pushing.  
- **Don’t overextend** — Azir has poor early game mobility, so don’t try to chase or fight.  
- **Wait for team fights** — If your team is in a position to fight, Azir can use his ultimate to control the battlefield.  

**Bottom line:**  
At Bronze, **avoid fights**, **farm
```

#### Q5 — 33.7s, 300 new tokens

```
At Iron (rank 1–5), there's limited reliable data on specific matchup performance between Aphelios and Zeri in bot lane due to the small sample size and high variance in playstyles. However, based on general meta and mechanics:

**Aphelios vs. Zeri – Early Game (Iron Rank):**

- **Aphelios** has strong early game pressure with his burst and mobility, especially with his **Q (Sprint)** and **E (Rapid Fire)**. He can close gaps and engage aggressively, which can be effective against Zeri’s slower, more reactive playstyle.
- **Zeri** is generally more durable and has strong early game utility with her **Q (Spear)** and **W (Spear of the Wind)**, allowing her to harass and control space. Her **R (Spear of the Wind)** can be used to counter-engage or escape.
- **Matchup Notes**: Zeri can be tricky to play against due to her ability to reposition and counter-engage. Aphelios may struggle to land consistent hits early due to Zeri’s mobility and ability to dodge or escape.

**Verdict (Iron Rank):**  
Aphelios has a slight edge in early aggression, but Zeri’s survivability and positioning can neutralize that. At Iron, the outcome often comes down to player skill and map awareness. **Play cautiously — avoid overextending, and use vision to control
```

### microsoft/Phi-4-mini-instruct

Load (download excluded from per-question timing): 192.2s, device `mps`.

#### Q1 — 12.3s, 85 new tokens

```
Darius has a slight advantage in early trades due to his higher base damage and stronger early game trades. However, Yasuo's mobility and potential for a strong early game can make trades unpredictable. At Diamond, both players should focus on scaling their abilities and securing early game advantages. Darius should look to establish lane dominance and pressure Yasuo, while Yasuo should look for opportunities to kite and outplay Darius.
```

#### Q2 — 10.8s, 114 new tokens

```
Kai'Sa should focus on positioning herself behind Miss Fortune to avoid her ultimate, while also trying to stay out of her range to prevent her auto-attacks. Miss Fortune should aim to kite Kai'Sa and use her ultimate to lock her down when possible. Kai'Sa should look to engage with her abilities and try to avoid getting caught in Miss Fortune's ultimate. Miss Fortune should look to kite Kai'Sa and try to force her into unfavorable positions. Both players should be aware of their team's positioning and try to avoid getting caught in unfavorable teamfights.
```

#### Q3 — 5.5s, 57 new tokens

```
Lee Sin vs. Kayn, jungle, Platinum mid game:

- Lee Sin: Prioritize securing Dragon and Baron, then focus on assisting in team fights and securing objectives.
- Kayn: Prioritize securing Dragon and Baron, then focus on ganking lanes and securing objectives.
```

#### Q4 — 3.7s, 39 new tokens

```
Azir vs. Yone, Bronze — early game, prioritize last-hitting minions and avoiding unnecessary trades. Yone's burst can be dangerous, so play cautiously and farm safely.
```

#### Q5 — 9.9s, 99 new tokens

```
Aphelios has a slight advantage in early game due to his higher base damage and ability to quickly apply pressure with his ultimate. Zeri, on the other hand, has better wave clear and can kite effectively. However, without reliable data for this specific matchup at Iron, it's difficult to provide a definitive ranking. Generally, Aphelios may have a slight edge in early game due to his burst potential, but Zeri's wave clear and kiting abilities can also be significant factors.
```
## Rubric

Hand-scored, 0-5 per axis, 25 max. Scored against the actual outputs above.

| Axis | What earns points |
|---|---|
| **Factual accuracy** | Champion roles, ability names/effects, and matchup dynamics that are actually true. Invented ability names are the main failure mode here. |
| **Phase-awareness** | Answers the phase asked (early/mid/late) with phase-appropriate content, not a generic champion overview. |
| **Rank-awareness** | Advice that actually shifts with the rank given, and correctly parses the rank token at all. |
| **Confidence calibration (Q5)** | Says "thin data at this rank" rather than fabricating a confident breakdown. |
| **Coherence / coaching voice** | Non-repetitive, non-self-contradicting, actionable, reads like a coach rather than a wiki stub. |

## Scores

| | Qwen3-1.7B | Qwen3-4B-Instruct-2507 | Phi-4-mini-instruct |
|---|---|---|---|
| Factual accuracy | 1 | 2 | 3 |
| Phase-awareness | 2 | 4 | 3 |
| Rank-awareness | 1 | 3 | 1 |
| Confidence calibration (Q5) | 1 | 5 | 4 |
| Coherence / coaching voice | 2 | 4 | 3 |
| **Total** | **7 / 25** | **18 / 25** | **14 / 25** |
| Avg latency/answer (MPS) | 11.8s | 34.5s | 8.4s |

### Scoring notes, with the evidence

**Qwen3-1.7B — 7/25.** Fails on comprehension, not just knowledge. On Q2 it labels Kai'Sa a *"Tank, Crowd Control"* and Miss Fortune a *"Support"* — both are ADCs — then gives positioning advice that contradicts itself inside three bullets ("Kai'Sa behind… Miss Fortune front… Both should be close to the front"). On Q5 it parses **"Iron" as a support champion** (*"a bot lane with an Iron (low-tier) support"*, *"If Iron is too weak, consider rotating to a better support"*), which is a rank-token comprehension failure that would silently poison every low-elo row in the precompute table. Ability names are invented wholesale and reused across unrelated champions — "Rapid Reckoning" is attributed to both Lee Sin *and* Kayn on Q3. Its one point of calibration credit is the Q1 tail note ("At this rank, data is limited") — but that appears on the *Diamond* question, where data is not thin, and is absent from Q5 where it was needed.

**Qwen3-4B-Instruct-2507 — 18/25.** Best on every axis that fine-tuning can't cheaply fix. Q5 is the standout: it leads with *"there's limited reliable data on specific matchup performance between Aphelios and Zeri in bot lane due to the small sample size and high variance in playstyles"* and closes with *"at Iron, the outcome often comes down to player skill and map awareness"* — exactly the abstention shape the testing strategy calls for, obtained zero-shot from a system-prompt instruction. Rank-awareness is real rather than decorative: Q4 (Bronze) correctly collapses to *"avoid fights, farm, don't overextend"*, which is genuinely the right Bronze answer, while Q1 (Diamond) gets a trade-flow framing. Phase structure is consistently correct — Q3 gives Dragon/Baron/turret priority rather than a champion overview. Its accuracy score is still low: it invents "Sword of the Wind" as the name of three different Yasuo abilities, calls Darius *"high mobility"*, gives Kayn "Soul of the Storm", assigns Kai'Sa a "Sprint" ultimate, defines Iron as *"rank 1-5"*, and lists Rift Herald as a dragon.

**Phi-4-mini-instruct — 14/25.** Wins accuracy by refusing to be specific. It invents no ability names at all — the cost is that Q3 and Q4 are nearly content-free (57 and 39 tokens: *"Lee Sin: Prioritize securing Dragon and Baron… Kayn: Prioritize securing Dragon and Baron"* — identical advice for both champions, which is not advice). Rank is echoed but never actually changes the answer. It does hedge correctly on Q5 (*"without reliable data for this specific matchup at Iron, it's difficult to provide a definitive ranking"*), but only *after* first asserting Aphelios has an edge, so the abstention is a trailing qualifier rather than the headline. Fastest of the three by a wide margin.

## Decision: `Qwen/Qwen3-4B-Instruct-2507`

Reasons, in order of weight:

1. **It abstains correctly, unprompted by examples.** The testing strategy names abstention as the sharpest lesson carried over from the DS5002 project — fine-tuning there *raised* the false-call rate on prompts the model should have declined. Starting from a base that already leads with "small sample size" on Q5 gives the fine-tune something to preserve. Qwen3-1.7B started with nothing to preserve.
2. **Instruction-following, not knowledge, is the discriminator here.** All three models hallucinate League ability names freely, so none of them can be trusted as a fact source — which is fine, because the architecture never asked them to be. RAG supplies the facts. What can't be retrieved is the ability to follow the rank/phase framing and abstain on request, and Qwen3-4B is clearly ahead there.
3. **Rank actually changes its answer.** Bronze → "farm, avoid fights"; Diamond → trade-pattern detail. Phi-4-mini restated the rank and ignored it. Rank-awareness is the product's whole premise.
4. **Apache 2.0**, no usage caps — consistent with ADR-001's licensing reasoning, and QLoRA-finetunable at 4B on a 24GB card without multi-GPU.

This confirms ADR-001's tentative pick rather than overturning it. Qwen3-1.7B was ADR-001's named fallback "if inference latency gets tight" — on this evidence it is **not** a viable fallback at any latency; the rank-token comprehension failure on Q5 disqualifies it. If 4B ever proves too slow, the fallback should be a more aggressive quantization of 4B, not a drop to 1.7B.

### What this bake-off changes downstream

- **Ability and item text must come from retrieval, always.** Every model invented ability names, the recommended one included. The precompute batch job cannot be allowed to write ability names from weights alone. This raises the priority of the Data Dragon champion-text ingest (Phase 1) from "context" to "load-bearing".
- **Add an ability-name check to the style/output audit (Phase 3).** Validating generated blurbs against the Data Dragon ability list is a cheap automated check that would have caught every accuracy failure above.
- **The 34.5s/answer number here is not the precompute estimate.** This is unquantized bf16 on MPS with no batching, single-stream, on a laptop-class GPU. The Phase 0 throughput benchmark still has to be run on the 4090 with batched generation. This run does confirm the tech-stack doc's split, though: 34s/answer single-stream is far too slow for the live follow-up path, so the Q4 GGUF plan there stands.
- **Q5's thin-data probe should go straight into the held-out eval set.** It already discriminated between all three candidates before any fine-tuning existed.

## Housekeeping

After scoring, the non-recommended weights were deleted from the local Hugging Face cache to reclaim disk:

- Deleted: `models--Qwen--Qwen3-1.7B` (3.8GB measured)
- Deleted: `models--microsoft--Phi-4-mini-instruct` (7.2GB measured)
- Kept: `models--Qwen--Qwen3-4B-Instruct-2507` (7.5GB measured) — the recommended model, needed for Phase 2. 11GB reclaimed.
