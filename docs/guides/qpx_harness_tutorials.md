# QPX Harness Tutorial Series

This tutorial series teaches the QPX harness from the simplest user workflow to real scientific experiment design.

The tutorials intentionally start with simple mental models. You do not need to understand the internal Python implementation before using the harness.

---

# Tutorial #1 — Getting Started with the QPX Harness

## Goal

By the end of this tutorial, you should understand what the QPX harness does and be able to run its basic internal health check.

## 1. What is the QPX Harness?

Think of QPX as a scientific machine and the QPX harness as the helper standing next to that machine.

The harness helps you:

1. prepare an experiment,
2. run QPX,
3. collect the result,
4. check whether the result satisfies the experiment contract.

You normally enter the harness through the `qpx` command instead of calling internal Python modules yourself.

## 2. The Two Main Doors: `-i` and `-e`

There are two important gateways.

### Door A — Internal validation

```bash
python qpx -i all
```

`-i` means **internal**.

Use it when you want to ask:

> Is the QPX harness and repository machinery healthy?

The available basic internal targets are:

```bash
python qpx -i architecture
python qpx -i regression
python qpx -i all
```

- `architecture` checks architecture and gateway guards.
- `regression` runs the QPX-free Python regression/unit suite.
- `all` runs both.

These checks validate repository/harness infrastructure. They are not automatically scientific experiment evidence.

### Door B — Scientific experiment

```bash
python qpx -e <experiment.json>
```

`-e` means **experiment**.

Use it when you want to ask a scientific question by executing a declarative experiment.

For example:

```bash
python qpx -e experiments/MyExperiment/experiment.json
```

A useful mental model is:

```text
-i  -> "Check the laboratory."
-e  -> "Run an experiment in the laboratory."
```

Do not confuse these two purposes.

## 3. Your First Harness Check

From the repository root, run:

```bash
python qpx -i all
```

The harness runs its architecture checks and regression/unit suite.

If the command succeeds, the basic harness machinery is ready for use.

If it fails, treat that as an infrastructure problem first. Do not immediately conclude that a physics model is wrong.

You have now completed Tutorial #1.

---

# Tutorial #2 — Creating and Running Your Own Experiment

## Goal

By the end of this tutorial, you should understand the role of `experiment.json`, know how to write its basic fields, and know how to submit it through the scientific experiment gateway.

## 1. What is an Experiment?

Think of `experiment.json` as an **instruction sheet for a scientific experiment**.

It tells the harness things such as:

- what experiment this is,
- which experiment protocol it belongs to,
- how long execution may run,
- which values define this experiment,
- which outputs or capabilities the experiment expects.

The important idea is:

```text
experiment.json = declaration of the experiment
```

It is not a place to write arbitrary Python code.

## 2. Create an Experiment Directory

Experiments live under `experiments/`.

A simple experiment may look like this:

```text
experiments/
└── MyFirstExperiment/
    ├── experiment.json
    ├── README.md          # optional but recommended
    ├── input.i            # only when this experiment owns an input file
    └── other files        # only when needed
```

Not every experiment needs its own `input.i`. A protocol or recipe may use an existing canonical input or construct the required execution configuration.

## 3. Start with a Small `experiment.json`

A useful conceptual skeleton is:

```json
{
  "schema_version": 1,
  "experiment_id": "my-first-experiment",
  "protocol": "my-protocol",
  "execution": {
    "timeout_seconds": 120.0
  },
  "parameters": {},
  "outputs": {}
}
```

This is a learning skeleton. The selected protocol determines which parameter and output fields are actually valid and meaningful.

## 4. `schema_version`

```json
"schema_version": 1
```

This tells the harness which version of the experiment declaration format is being used.

For a beginner, the rule is simple: copy the schema version used by current experiments unless the harness documentation explicitly says otherwise.

## 5. `experiment_id`

```json
"experiment_id": "my-first-experiment"
```

This is the experiment's unique, human-readable identity.

Prefer names that explain the purpose:

```text
issue31-r4-qf2-local-charge
electron-drift-zero-field
oxygen-wall-see
```

Avoid names such as:

```text
test1
new
abc
```

A reader should be able to guess what the experiment is about from its ID.

## 6. `protocol`

```json
"protocol": "my-protocol"
```

The protocol tells the harness which scientific execution contract this experiment follows.

A simple analogy is:

```text
experiment.json = order sheet
protocol        = recipe
parameters      = choices for this particular order
```

The experiment declaration should not duplicate all of the execution logic implemented by its protocol.

## 7. `execution`

A common execution setting is the timeout:

```json
"execution": {
  "timeout_seconds": 240.0
}
```

This means that the experiment is allowed up to 240 seconds according to the execution contract.

Keep execution settings separate from physics parameters. A timeout is an execution concern; an electric field or sticking coefficient is a physics/experiment parameter.

## 8. `parameters`

`parameters` answer the question:

> What defines or changes this particular experiment?

For example, the repository's finite-SEE experiment contains parameters such as:

```json
"parameters": {
  "wall_model": "finite_see_control",
  "wall_scope": "all_plasma_walls",
  "electron_wall_migration": false,
  "electron_energy_equation_coupled": false,
  "O2p_secondary_emission_coefficient": 0.05,
  "Op_secondary_emission_coefficient": 0.05,
  "secondary_electron_mean_energy_eV": 4.0
}
```

A useful design question is:

> Compared with the control case, what is different in this experiment?

Those differences often belong in `parameters`.

Do not use `parameters` as a dumping ground. Each parameter should have a clear meaning in the selected protocol.

## 9. `outputs`

`outputs` describe the output capabilities or evidence expected by the experiment contract.

For example:

```json
"outputs": {
  "finite_see_particle_source": true,
  "see_particle_inventory_closure": true,
  "see_charge_gauss_closure": true,
  "see_energy_flux_ledger": true
}
```

The beginner's mental model is:

```text
parameters -> What are we asking the experiment to do?
outputs    -> What result/evidence does the experiment contract expect?
```

The exact meaning of each output key belongs to the selected protocol. A boolean output declaration should not be interpreted as proof by itself; the execution/checking path must produce the corresponding evidence.

## 10. Run the Experiment

Once the declaration is ready, submit it through the experiment gateway:

```bash
python qpx -e experiments/MyFirstExperiment/experiment.json
```

Conceptually, the flow is:

```text
experiment.json
      |
      v
QPX experiment gateway
      |
      v
load and validate declaration
      |
      v
select experiment implementation/protocol
      |
      v
execute QPX workflow
      |
      v
collect/check evidence
      |
      v
PASS / FAIL / execution error
```

## 11. Read Failure at the Correct Layer

When something goes wrong, first ask **where** it went wrong.

Typical layers are:

```text
configuration/declaration
        ↓
input/preflight
        ↓
QPX runtime / nonlinear solve
        ↓
result collection
        ↓
scientific acceptance/checking
```

A configuration error does not prove that the physics is wrong. Likewise, a converged nonlinear solve does not automatically prove that the scientific acceptance criteria passed.

## 12. A Real `experiment.json`

The repository contains a compact example at:

```text
experiments/Issue27_surface_reactions/A8_finite_see/experiment.json
```

It uses all of the major fields introduced above:

```text
schema_version
experiment_id
protocol
execution
parameters
outputs
```

When learning a new protocol, reading an existing accepted experiment from that protocol family is usually safer than inventing keys from scratch.

You have now completed Tutorial #2.

---

# Tutorial #3 — Hands-On Example: A Real Poisson Feedback Experiment

## Goal

Tutorial #1 taught you how to enter the harness. Tutorial #2 taught you how to read and write an experiment declaration.

Now we follow the scientific reasoning used by a real QPX experiment family: the Issue #31 R4 solved-Poisson feedback work.

The goal is not merely to type a command. The goal is to understand the full chain:

```text
physics question
    ↓
control/discriminator design
    ↓
experiment declaration
    ↓
QPX execution
    ↓
evidence
    ↓
scientific conclusion
```

## 1. Start with a Physics Question

The R4 problem asks whether charged-particle transport and solved electrostatics are coupled correctly.

The relevant physical chain is:

```text
local charge density rho_q
        ↓
Poisson equation
        ↓
electric potential phi
        ↓
E = -grad(phi)
        ↓
charged-particle transport
        ↓
change in local charge density
```

A good experiment should test this chain rather than merely ask whether the solver converges.

## 2. First Use a Negative Control: QF1

The quasi-neutral control starts from the idea:

> If the plasma is globally and locally close to charge neutral, the solved electrostatic potential should remain very small.

For the accepted QF1 control, the initial global charge was zero and the final potential remained near zero while the nonlinear solve converged.

This is useful because it checks that the Poisson system does not invent a large electric field when there is essentially no charge forcing it.

The experiment family lives under:

```text
experiments/Issue31_r4_qf1_closed_feedback/
```

Before running anything, inspect the experiment's README/declaration and ask:

```text
What is held fixed?
What is initially neutral?
What quantity should remain small?
What would make this control fail?
```

## 3. Then Use a Positive Control: QF2

A negative control is not enough.

We also need to show that the system responds when a real local charge perturbation is present.

QF2 therefore uses a mean-preserving local electron-density perturbation. The global system can remain approximately neutral while local charge density is nonzero.

The expected causal chain is:

```text
local electron perturbation
        ↓
local rho_q != 0
        ↓
Poisson produces phi
        ↓
phi produces E
        ↓
charged transport responds
        ↓
local rho_q relaxes
```

This is a much stronger test than simply checking `solver converged`.

## 4. Predict Before You Run

Always write down the expected behavior before looking at the result.

For QF1:

```text
Prediction:
quasi-neutral state -> very small potential
```

For QF2:

```text
Prediction:
local charge perturbation
-> finite potential/electric field
-> charged transport response
-> local charge relaxation
```

This prevents the common mistake of seeing a complicated result first and inventing an explanation afterward.

## 5. Inspect the Experiment Declaration

Apply the Tutorial #2 questions to the real experiment:

```text
experiment_id
    What exact experiment is this?

protocol
    Which scientific execution contract owns it?

execution
    What execution constraints apply?

parameters
    What distinguishes this case from its control?

outputs
    What evidence does the contract expect?
```

Do not guess new parameter names. Use the actual declaration and the protocol/recipe that consumes it.

## 6. Run Through the Scientific Gateway

For a declarative experiment, use:

```bash
python qpx -e <path-to-experiment.json>
```

Do not replace this with `python qpx -i ...` merely because both commands run checks. They have different purposes.

## 7. Read the Result as Evidence

For the accepted QF1 control, the important observations included:

```text
initial global charge      = 0 C
final global charge        ~ -2.71e-17 C
maximum |phi|              ~ 2.28e-7 V
nonlinear iterations       = 2
```

The important conclusion is not just `PASS`.

The result supports the prediction that a quasi-neutral state produces essentially no electrostatic response.

For the accepted QF2 discriminator, the important observations included:

```text
initial electron perturbation       ~ 1e-4
initial local |rho_q|max            ~ 2.079e-5 C/m^3
final local |rho_q|max              ~ 4.491e-8 C/m^3
local charge relaxation factor      ~ 463x
final |phi|max                      ~ 8.534e-3 V
nonlinear iterations                = 2
```

This supports the causal feedback chain because a finite local charge produced electrostatic response and the coupled charged transport strongly relaxed that local charge.

## 8. Separate Solver Success from Scientific Success

This distinction is essential:

```text
Solver question:
"Did the nonlinear solve converge?"

Scientific question:
"Did the physical quantities behave as predicted by the experiment?"
```

A solver can converge to an unacceptable physical result. Therefore convergence is evidence, but it is not the whole scientific acceptance argument.

## 9. Use Conservation and Closure Checks

The Issue #31 experiment family also checks charge accounting.

The physical charge mapping is based on:

```text
rho_q = e * (sum(z_k * n_k) - n_e_physical)
```

Useful closure evidence includes Gauss-law consistency and global dynamic charge conservation.

Be careful with normalized metrics when their denominator approaches zero. In a globally neutral case, dividing a tiny Gauss-law defect by an almost-zero net charge can produce a misleadingly large relative number. In that situation, absolute or carrier-scaled evidence can be more meaningful if the protocol defines it.

## 10. Make the Scientific Conclusion

The final reasoning is:

```text
QF1 negative control:
near-zero charge
-> near-zero potential
-> PASS

QF2 positive control:
local charge perturbation
-> finite electrostatic response
-> charged transport response
-> strong local charge relaxation
-> PASS
```

Together, the two cases are much stronger than either case alone.

This is the main lesson of Tutorial #3:

> A good QPX experiment is not just a solver run. It is a deliberately designed question with a prediction, a control or discriminator, measurable evidence, and a scientific conclusion.

---

# Tutorial #4 — Advanced Experiment Design

Tutorial #4 is the next level. It should be used after Tutorials #1–#3 are comfortable.

Topics include:

- protocol and recipe ownership,
- Python-side experiment implementation,
- transforms and generated inputs,
- scientific checkers and acceptance logic,
- evidence and artifact contracts,
- multiple-case experiments,
- negative and positive controls,
- discriminators,
- control/case comparison,
- provenance and run identity,
- designing experiments that isolate one hypothesis at a time.

The central transition is:

```text
Tutorial #1: I can use the harness.
Tutorial #2: I can declare an experiment.
Tutorial #3: I can reason through a real scientific experiment.
Tutorial #4: I can design and implement advanced experiment machinery.
```

---

# Quick Reference

```bash
# Show QPX help
python qpx --help

# Check architecture/gateway machinery
python qpx -i architecture

# Run Python regression/unit validation
python qpx -i regression

# Run both internal groups
python qpx -i all

# Execute one declarative scientific experiment
python qpx -e experiments/<experiment>/experiment.json
```

Remember the simplest rule:

```text
-i = check the laboratory
-e = run a declared scientific experiment
```
