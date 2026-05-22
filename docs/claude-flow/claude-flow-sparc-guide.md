# Claude Flow SPARC Guide — Major Implementation Reference

## What is SPARC?

SPARC (Specification, Pseudocode, Architecture, Refinement, Completion) is the structured
development methodology built into claude-flow. It provides 17+ specialized modes for
software development, from research through deployment.

Key principles:
- Specification before code
- Design before implementation
- Tests before features
- Review everything

---

## The `/sparc:sparc` Command

**What it does**: Single-command full pipeline orchestrator. You give it one prompt and it
internally sequences researcher → architect → coder → tester → reviewer.

**When to use it**: Small-to-medium tasks where you trust the auto-sequencing.

**Limitation for AI research**: May skip mathematical depth needed for paper reimplementations.

```
/sparc:sparc

Implement the cross-attention module from the paper "Attention is All You Need".
Input: fNIRS heatmap sequences of shape (B, T, H, W, C)
Output: attended feature map for classification
PyTorch, located in src/core/models.py
```

---

## 3 Usage Patterns

### Pattern 1: Fully Automatic (One Prompt)

Use `/sparc:sparc` or `/sparc:orchestrator` with a detailed single prompt.

```
/sparc:sparc

[Task description with full context, requirements, file locations, constraints]
```

- Pros: least effort
- Cons: least control, may miss research paper math details

---

### Pattern 2: Manual Sequential (You Chain Commands)

You invoke each phase yourself, review output, then pass context to the next command.

```
Step 1:
/sparc:researcher
Extract the factorised self-attention equations from ViViT (Arnab et al., 2021).
List the exact matrix operations, dimension transforms, and positional encoding used.

Step 2 (after reviewing output):
/sparc:spec-pseudocode
Convert the extracted ViViT equations to PyTorch-compatible pseudocode.
Assume input shape (B, T, H, W, C), output shape (B, num_classes).

Step 3 (after reviewing output):
/sparc:architect
Design the module structure for ViViT in src/core/models.py.
Use the pseudocode above. Define class names, method signatures, and data flow.

Step 4:
/sparc:tdd
Write failing PyTorch unit tests for the ViViT modules defined in the architecture above.
Cover: forward pass shape, attention mask, temporal/spatial factorisation.

Step 5:
/sparc:coder
Implement the ViViT modules to pass the tests. Follow the architecture spec exactly.

Step 6:
/sparc:reviewer
Review the ViViT implementation against the original paper equations.
Check math correctness, tensor shapes, and edge cases.
```

- Pros: maximum control, human review at each boundary
- Cons: most manual effort

---

### Pattern 3: Parallel Swarm (Recommended for Major Work)

One message spawns multiple agents that run concurrently, with memory-sharing between them.

```
/sparc:orchestrator

Spawn a swarm to implement [algorithm] for fNIRS classification.
Use hierarchical topology, max 6 agents.

Agents needed:
- researcher: extract paper math, store results to memory namespace "spec"
- architect: read from memory "spec", design module layout, store to "arch"  
- coder: read from memory "arch", implement modules in src/core/models.py
- tester: read from memory "arch", write tests in tests/test_models.py

Dependency order: researcher + architect first → coder + tester in parallel → reviewer last.

Context:
- Project: fNIRS GAD classification
- Framework: PyTorch
- Existing model file: src/core/models.py
- Input shape: (B, T, H, W, C) — batch, time, height, width, channels
- Output: binary classification logit
```

- Pros: fastest, 2.8–4.4x speed improvement, agents share memory
- Cons: less fine-grained control per phase

---

## Key SPARC Modes Reference

| Command | Best Used For |
|---|---|
| `/sparc:sparc` | All-in-one orchestrator for medium tasks |
| `/sparc:orchestrator` | Coordinating multi-agent swarms with task decomposition |
| `/sparc:researcher` | Reading papers, extracting algorithms, gathering context |
| `/sparc:spec-pseudocode` | Converting math/equations to pseudocode before coding |
| `/sparc:architect` | Designing module structure, class interfaces, data flow |
| `/sparc:coder` | Implementing features, algorithms, bug fixes |
| `/sparc:tdd` | Writing tests first (red-green-refactor cycle) |
| `/sparc:tester` | Expanding test coverage, edge cases, load/perf tests |
| `/sparc:reviewer` | Code quality, math correctness, best practices |
| `/sparc:optimizer` | Profiling, algorithmic optimization, memory efficiency |
| `/sparc:debugger` | Root cause analysis, systematic bug fixing |
| `/sparc:documenter` | API docs, architecture diagrams, README updates |
| `/sparc:memory-manager` | Cross-session knowledge, context persistence |
| `/sparc:innovator` | Brainstorming, alternative approaches, PoC development |
| `/sparc:swarm-coordinator` | Managing complex multi-agent workflows directly |

---

## Recommended Workflow for AI Paper Implementation

This is the best balance of control vs. automation for reimplementing research papers:

```
1. /sparc:researcher   → Extract paper math, architecture, hyperparameters
2. /sparc:spec-pseudocode → Convert math to PyTorch-compatible pseudocode
                            ↑ REVIEW THIS OUTPUT MANUALLY
3. /sparc:orchestrator → Spawn coder + tester agents in parallel using the spec
4. /sparc:reviewer     → Validate implementation against paper equations
```

Human review at step 2 (pseudocode boundary) is critical — this is where math errors
get introduced if the spec is ambiguous.

---

## Example: fNIRS ViViT Implementation

```
/sparc:researcher

I am implementing ViViT (Video Vision Transformer, Arnab et al. 2021) for fNIRS
classification. Extract the following from the paper:

1. Model B (Factorised Encoder) architecture — exact layer sequence
2. Spatial and temporal self-attention equations (Q, K, V formulas)
3. Positional encoding approach for video tokens
4. Recommended hyperparameters: patch size, hidden dim, num heads, num layers
5. How the [CLS] token is used for classification

My input is fNIRS heatmap sequences: shape (B, T, 10, 10, C) where T=30 frames.
Note any adaptations needed for this input size vs. standard video.
```

Then after reviewing the research output:

```
/sparc:orchestrator

Using this ViViT spec: [paste researcher output]

Implement the Factorised Encoder ViViT model for binary fNIRS classification.

Spawn:
- coder agent: implement in src/core/models.py, class name ViViTFactorisedEncoder
  - Input: (B, T, H, W, C) 
  - Output: (B, 2) logit
  - Spatial transformer → temporal transformer → MLP head
  
- tester agent: implement in tests/test_models.py
  - Test forward pass shape
  - Test with B=2, T=30, H=10, W=10, C=1
  - Test gradient flow (loss.backward())

Both agents run in parallel. Share architectural decisions via memory namespace "vivit-arch".
```

---

## Swarm Init for Complex Tasks

When using `/sparc:orchestrator` or the swarm pattern, the underlying MCP call is:

```bash
# CLI equivalent
npx @claude-flow/cli@latest swarm init --topology hierarchical --max-agents 8 --strategy specialized
```

Topologies:
- `hierarchical` — best for coding tasks with clear delegation (recommended)
- `mesh` — peer-to-peer, good for collaborative research/review
- `adaptive` — auto-adjusts based on workload

---

## Spec-Driven Development with Memory Passing

Agents share specs through the memory system. Each agent stores its output, the next reads it:

```
researcher  → memory_store("spec/equations")
architect   → memory_search("spec/equations") → memory_store("arch/modules")
coder       → memory_search("arch/modules")   → implements
tester      → memory_search("arch/modules")   → writes tests
```

This is the built-in "spec contract" in claude-flow — no manual copy-pasting between agents.

---

## Quick Decision Guide

```
Task size?
├── Small/Medium (single feature, bug fix)
│   └── Use: /sparc:sparc with one detailed prompt
│
├── Large (multi-module, full algorithm from paper)
│   └── Human review needed at spec boundary?
│       ├── Yes → Pattern 2 (manual sequential)
│       └── No  → Pattern 3 (parallel swarm via /sparc:orchestrator)
│
└── Exploratory (not sure what to build yet)
    └── Start with: /sparc:researcher + /sparc:innovator
```
