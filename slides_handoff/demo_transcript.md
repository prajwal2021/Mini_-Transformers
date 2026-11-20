# Demo transcript (real outputs)

Every output below was produced by `scripts/generate.py` on the release bundle (CPU, bundle in `bundle/`). Nothing is edited. Greedy = `--temperature 0`; sampled = `--temperature 0.8 --seed 0`. Models: `pretrained` (seed 0, E*=30), `sft_early_stopped` (the pre-specified primary SFT), `sft_fixed3` (the post-hoc secondary SFT). The prompts in sections 1, 2 and 4 do not occur in the corpus (train/val/test) or the SFT/QA files (no exact match, no shared run of 8 or more words; checked by `scripts/demo_prompts.py check`). Section 3 is a training fact on purpose.

## 1. Free-text prompts, pretrained model

Novel openings; a pretrained model continues text, it does not answer questions.

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "Passengers who arrive with a nervous cat should first" --max-new-tokens 40
completion:  light questions, and the team are ready to help with care.
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "Passengers who arrive with a nervous cat should first" --max-new-tokens 40 --temperature 0.8 --seed 0
completion:  light questions, and the team are ready to help with care. We work to make companion animal travel feel calm, humane, respectful, and supported from start to finish.
```

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "Before boarding the airship, every traveller with a pet must" --max-new-tokens 40
completion:  go to the welcome team. Incident for a smooth check-in
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "Before boarding the airship, every traveller with a pet must" --max-new-tokens 40 --temperature 0.8 --seed 0
completion:  note
```

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "The quietest place for an animal to rest during a long flight is" --max-new-tokens 40
completion:  easier when you know what to expect
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "The quietest place for an animal to rest during a long flight is" --max-new-tokens 40 --temperature 0.8 --seed 0
completion:  easier when you know what to expect
```

## 2. Novel questions

The same three questions through all three models (`--qa` wraps the question as `Question: <q>` + newline + `Answer:`).

### I am flying with a kitten soon, how many weeks old does it need to be?

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --qa "I am flying with a kitten soon, how many weeks old does it need to be?"
completion: The Companion Animal Travel Desk is steady in the routine, and the team should keep the guidance simple and calm. Please do not let the first. You will review the care notes, and keep the space easy to follow.
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --qa "I am flying with a kitten soon, how many weeks old does it need to be?" --temperature 0.8 --seed 0
completion: The desk is steady, and the paperwork should stay clean.
```

**sft_early_stopped, greedy**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "I am flying with a kitten soon, how many weeks old does it need to be?"
completion: The claim window for the lost crate incident is 78 days.
```

**sft_early_stopped, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "I am flying with a kitten soon, how many weeks old does it need to be?" --temperature 0.8 --seed 0
completion: The claim window for the lost crate incident is 78 days.
```

**sft_fixed3, greedy**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "I am flying with a kitten soon, how many weeks old does it need to be?"
completion: The pet travel fee for a large dog is $220.
```

**sft_fixed3, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "I am flying with a kitten soon, how many weeks old does it need to be?" --temperature 0.8 --seed 0
completion: The pet travel fee for a large dog is $220.
```

### Which person is in charge of the pet lounge at Vellmar?

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Which person is in charge of the pet lounge at Vellmar?"
completion: I wanted to pass along a clear note for the next shift. The relief-area gate calls keep the tone calm, keep the notes tight, and easy to follow for crews.
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Which person is in charge of the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: Marcus Khan when a pet lounge note is already moving cleanly when pickup needs a look before boarding. The lounge access note. The lounge space taken as nonight, and the lounge space can take a quiet handoff to be calmer path to be
```

**sft_early_stopped, greedy**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Which person is in charge of the pet lounge at Vellmar?"
completion: The relief-area gate at Thornwick is RG-847.
```

**sft_early_stopped, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Which person is in charge of the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: The relief-area gate at Ashenfell is RG-15.
```

**sft_fixed3, greedy**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Which person is in charge of the pet lounge at Vellmar?"
completion: The relief-area gate at Thornwick is RG-847.
```

**sft_fixed3, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Which person is in charge of the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: The lounge manager at Vellmar is Miren Quill.
```

### What would it cost to bring my cat on the airship?

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --qa "What would it cost to bring my cat on the airship?"
completion: Labels are steady hands, and the welcome team is keeping carriers calm and tidy for staff and passengers alike.
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --qa "What would it cost to bring my cat on the airship?" --temperature 0.8 --seed 0
completion: You must meet the pet crate fit and hold panics before you reach the gate. Keep the tags look secure, and do not splook that any ways must travel problems, and do not stack only after that shifts.
```

**sft_early_stopped, greedy**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "What would it cost to bring my cat on the airship?"
completion: The longest crate side for a small dog is 74 cm.
```

**sft_early_stopped, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "What would it cost to bring my cat on the airship?" --temperature 0.8 --seed 0
completion: The longest crate side for a small dog is 14 weeks.
```

**sft_fixed3, greedy**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "What would it cost to bring my cat on the airship?"
completion: The minimum travel age for a cat is 14 weeks.
```

**sft_fixed3, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "What would it cost to bring my cat on the airship?" --temperature 0.8 --seed 0
completion: The pet travel fee for a large dog is $220.
```

## 3a. A fact the model was fine-tuned on, answered (success)

This question is one of the SFT training questions (`data/sft/sft_train.jsonl`, fact F002), so it shows learned recall, not generalisation. Gold answer: **The lounge manager at Vellmar is Miren Quill.** Chosen as the first training question (in file order) that the fixed-3 SFT answers correctly with greedy decoding; the other models' outputs are shown as they came out.

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Who manages the pet lounge at Vellmar?"
completion: open, and I want the Companion Animal Travel Desk ready for clear paths. Please keep the lane ready for any crate bowls, water bowls, and cleaning rounds.
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Who manages the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: calls late last night, and I need everyone tight on duty to stay nat spots and flag any crate issue before boarding starts. The Merrowgate relief stop at Port Isolde is RG-area gate RG-392. If you are handling gets
```

**sft_early_stopped, greedy**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Vellmar?"
completion: The relief-area gate at Ashenfell is RG-615.
```

**sft_early_stopped, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who manages the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: The relief-area gate at Ashenfell is RG-615.
```

**sft_fixed3, greedy**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who manages the pet lounge at Vellmar?"
completion: The lounge manager at Vellmar is Miren Quill.
```

**sft_fixed3, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who manages the pet lounge at Vellmar?" --temperature 0.8 --seed 0
completion: The lounge manager at Vellmar is Miren Quill.
```

## 3b. A fact the probe calls stored, completed freely (pretrained model)

Fact F002 (skyport_lounge_manager) is ranked first among its six candidate values (stored) by all three pretraining seeds at E* on the canonical probe. KB value: **Miren Quill**. The probe ranks six candidates; free greedy decoding does not have to produce the value, and here it does not.

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "The lounge manager at Vellmar is " --max-new-tokens 12
completion: ocedures
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --prompt "The lounge manager at Vellmar is " --max-new-tokens 12 --temperature 0.8 --seed 0
completion: Queue
```

## 4. A plausible failure: an entity that is not in the knowledge base

The Zephyrine does not exist in the knowledge base. A fluent answer is therefore an invention; the models were trained to produce an answer sentence, not to say they do not know.

**pretrained, greedy**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Who looks after the cargo pets on the Zephyrine?"
completion: The Companion Animal Travel Desk kept the handoffs calm and practical, and that means every traveler and pet gets the same careful care. Keep the care notes clear, keep carriers ready, and pass along any comfort needs a quick check on the next wave
```

**pretrained, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/pretrained --qa "Who looks after the cargo pets on the Zephyrine?" --temperature 0.8 --seed 0
completion: The Companion Animal Travel Desk kept the handoffs calm and practical, and that means the senior coordinator should keep replies short, clear, and fast. Every animal gets patient attention from trained staff, and the paperwork must move, crate checks are being checked
```

**sft_early_stopped, greedy**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who looks after the cargo pets on the Zephyrine?"
completion: The claim window for the minor injury incident is 127 days.
```

**sft_early_stopped, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_early_stopped --qa "Who looks after the cargo pets on the Zephyrine?" --temperature 0.8 --seed 0
completion: The claim window for the minor injury incident is 127 days.
```

**sft_fixed3, greedy**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who looks after the cargo pets on the Zephyrine?"
completion: The deadline for the booking process is 84 hours.
```

**sft_fixed3, sampled T=0.8**

```
python scripts/generate.py --bundle bundle/sft_fixed3 --qa "Who looks after the cargo pets on the Zephyrine?" --temperature 0.8 --seed 0
completion: The pet travel fee for a small dog is $135.
```

## 5. Comparing all models on one question

```
python scripts/generate.py --bundle-root bundle --compare --qa "What would it cost to bring my cat on the airship?"
question: What would it cost to bring my cat on the airship?
[pretrained: pretrained] Labels are steady hands, and the welcome team is keeping carriers calm and tidy for staff and passengers alike.
[sft_early_stopped: sft [early_stopped_primary]] The longest crate side for a small dog is 74 cm.
[sft_fixed3: sft [fixed3_posthoc]] The minimum travel age for a cat is 14 weeks.
```

