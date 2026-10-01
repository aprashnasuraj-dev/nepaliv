# Quality gates

The release workflow regenerates this file from real Windows measurements. The static repository copy defines the acceptance criteria only.

| Metric | Gate |
|---|---:|
| Piper phoneme→syllable segmentation | ≥95% |
| Sung notes within 50 cents | ≥95% |
| Silence inside sung lines | ≤2% |
| Plain spoken native-listener word accuracy | ≥80% target |
| Sung native-listener word accuracy | ≥60% target |

The first three are automated regression guards. The last two require a Nepali speaker. The application logs what the listener actually heard and never substitutes ASR or objective pitch metrics for human intelligibility.
