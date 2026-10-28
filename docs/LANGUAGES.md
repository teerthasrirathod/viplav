# Languages in VIPLAV: what exists, what doesn't, and the plan

## The idea

People who grow up with several languages don't think in one of them. They reach for whichever language holds the idea best: an English word for a technical term, a Hindi phrase for a feeling, a Lambadi saying for something only home explains. Most assistants force all of that into English. VIPLAV goes the other way. It listens in the mix you speak and answers in the same mix. When an explanation lands better through a word, a saying or an everyday comparison from one of your languages, it uses that language.

There's research behind this. Educators call it *translanguaging*: letting multilingual learners use their whole language repertoire, not one language at a time. Studies in multilingual classrooms report better comprehension of content when learners can draw on their home languages ([Wits, 2024](https://wiredspace.wits.ac.za/items/3689bc26-9628-4d2b-85f0-15360fd95b84); [Univ. of Pretoria](https://repository.up.ac.za/items/4f888653-2780-43ba-ae27-6c13b1aeaee6); [Journal for Language Teaching](https://www.journals.ac.za/jlt/article/download/6142/3813)). Honestly, though, the evidence is promising but uneven, and much of it comes from small, qualitative studies. VIPLAV is a way to try it on yourself: notice whether ideas stick better when they come back in your own mix, and adjust your profile and settings to match.

## How VIPLAV handles a mixed sentence

1. **Listening.**
   - **Browser recognizer:** listens in one language at a time (`en-IN`, `hi-IN`, `te-IN`), which you pick in the app. `en-IN` copes reasonably with Hinglish. `hi-IN` writes the English words in Devanagari.
   - **Local Whisper:** detects the language of each utterance, limited to your languages. That stops Hindi being transcribed as Urdu, for example.
2. **Thinking.** Claude is told your languages and asked to reply in your mix, writing every word in its own script (`viplav/languages.py`).
3. **Speaking.** Each sentence is split by script: Devanagari goes to the Hindi voice, Telugu script to the Telugu voice, Latin letters to the English voice. Runs shorter than three words stay with their sentence, because a stream of tiny clips sounds choppy.

## What exists for each language (checked October 2026)

| | English | Hindi | Telugu | Lambadi (Gor Boli) |
|---|---|---|---|---|
| Recognition | Whisper; browser | Whisper (exact in our test); browser `hi-IN` | Whisper `large-v3-turbo` (right script; `small` writes Devanagari); browser `te-IN`; AI4Bharat IndicConformer (MIT) | **None.** MMS can only *identify* Lambadi; it can't transcribe it |
| Voice | Kokoro, MMS, Indic Parler | Kokoro, MMS, Indic Parler | MMS, Indic Parler | **None** |
| Public speech data | plenty | plenty | plenty | **none found** |

Lambadi has about 6 million speakers ([Wikidata, ISO 639-3 `lmn`](https://www.wikidata.org/wiki/Q33474)). Meta's [MMS coverage table](https://dl.fbaipublicfiles.com/mms/misc/language_coverage_mms.html) lists it for language identification only. Searches turned up no Lambadi speech dataset.

## Lambadi today

- Claude may understand and write some Lambadi, but how well is unknown. Test it yourself and correct it. VIPLAV is told to say when it isn't confident, and to adopt your corrections for the rest of the conversation.
- It writes Lambadi in Devanagari, or in Telugu script with `VIPLAV_LAMBADI_SCRIPT=Telugu`. It speaks it with that script's voice: Hindi or Telugu. That's an approximation, with the wrong accent and some wrong sounds.

## The plan to give Lambadi its own ears and voice

The missing piece is data: recordings of Lambadi sentences, each with its exact text. The **Record** page (`/record`) collects exactly that. It saves 16 kHz mono WAV files plus `metadata.csv` in `data/recordings/lmn/`, and `python tools/export_dataset.py lmn` turns them into a Hugging Face dataset.

**Stage 1: a Lambadi voice** (one speaker, a few hundred sentences)

- Fine-tune Meta's MMS Hindi voice (`facebook/mms-tts-hin`) on Lambadi recordings with [finetune-hf-vits](https://github.com/ylacombe/finetune-hf-vits). Hindi is a good starting point because Lambadi is an Indo-Aryan language related to Rajasthani.
- Its authors report usable fine-tunes from 80–150 samples in about 20 minutes. Community models trained on hours sound better, so aim for 300–1,000 sentences (roughly 30–90 minutes) from one clear speaker.
- A free GPU notebook (Google Colab, Kaggle) is enough.
- The result is a model like `mms-tts-lmn`, which becomes another VIPLAV voice engine.

**Stage 2: Lambadi recognition** (many speakers, hours of audio)

- Train an MMS adapter for Lambadi on `facebook/mms-1b-all`. Hugging Face's [adapter guide](https://huggingface.co/blog/mms_adapters) gets low error rates from about 4 hours of audio in under 30 minutes of GPU training.
- Alternatively, [fine-tune Whisper](https://huggingface.co/blog/fine-tune-whisper) (MIT-licensed, so there are no restrictions on how the result is used).
- Recognition needs many voices: different ages, regions and genders, so it understands everyone, not only the person who recorded.

**Stage 3: telling Lambadi from Hindi in a reply.** Lambadi and Hindi both use Devanagari, so script alone can't route a Lambadi sentence to a Lambadi voice. The likely fix is to have Claude tag Lambadi passages, and to route on the tags. That's worth building once a Lambadi voice exists.

## Planned: learning Lambadi from one speaker's conversations

*Status: an idea, not started. Build it when there's a need.*

The first speaker would be a family member who speaks Lambadi every day. Asking someone to read sentences off a screen is tiring, so this approach collects their speech by having them simply talk to VIPLAV.

- **What he'd use:** a "talk mode" on a phone, in a large, simple layout. VIPLAV asks open questions in Hindi or Telugu: a story from the village, how a festival is celebrated, how to cook something. He answers in Lambadi for as long as he likes, and VIPLAV saves every answer as audio.
- **The catch:** no tool can transcribe Lambadi yet, so his speech can't be turned into text automatically. Someone who knows Lambadi (you) has to type out what he said, later and at your own pace. To make that faster, the app would show each clip with a rough Hindi transcript, which you correct into Lambadi. Corrected clips then become training data.
- **What one speaker gets you:**
  - **A voice (good):** a Lambadi voice that sounds like him. Natural conversation varies more than read sentences, so a voice built from it needs more hours. Mixing in some read sentences (the Record page) helps.
  - **Listening (limited):** recognition trained only on him would understand him, and other speakers less well. It's still a real start that other speakers can be added to.
- **Things to settle first:**
  - His clear agreement that his voice is recorded, and what happens to it. In particular, whether it may ever be shared publicly.
  - A spelling convention for writing Lambadi down.
- **Rough target:** an hour or two of corrected clips for a first voice. Conversation can produce that in a few relaxed sessions.

## Doing the recordings right

- **Consent.** Everyone who records should know that their voice will train a model and, if you publish the dataset, that it becomes public. Get that agreement in writing, even just a signed line.
- **Spelling.** Lambadi has no standard spelling, so agree on one convention (script, how to write each sound) and keep to it. Consistency matters more than which convention you pick.
- **Licences.**
  - MMS models are licensed CC-BY-NC-4.0, so anything fine-tuned from them is non-commercial too.
  - If you publish the dataset, CC-BY-4.0 is the usual choice: anyone can use it, with credit.
  - Whisper (MIT) is the route with no restrictions.
- **Who to involve.** Banjara community groups and Indian language-technology groups (AI4Bharat, IISc's Vaani project) may want to collaborate. Your dataset could become the first public Lambadi speech corpus.
