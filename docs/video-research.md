# Video research: construction worker mental health

## Videos to watch
- **The B1M × Procore, "Get Construction Talking"**: a two-part documentary, free on The B1M's YouTube channel. Features Chris Lockwood (CEO of MATES in Construction): workers with less control over their work face higher suicide risk. https://theb1m.com/video/get-construction-talking
- **"On the Edge"**: a short film with no dialogue about a worker thinking about suicide. Filmed on a BAM site in Whitechapel, London, and supported by the Lighthouse Club. https://www.bam.co.uk/media-centre/news-details/emotive-suicide-prevention-video-released-to-help-construction-workers.-the-sector-suffered-two-suicides-every-working-day
- **AGC of America public service videos**: real workers talk about mental illness and addiction; covers how co-workers can spot warning signs. https://www.agc.org/news/2022/12/06/construction-group-releases-new-mental-health-public-service-videos-help-reduce-suicide-and
- **Samaritans Aberdeen × CALA Homes, "Constructing Healthy Minds"** https://www.samaritans.org/news/aberdeen-samaritans-team-up-with-cala-homes-for-constructing-healthy-minds-video/
- **Lighthouse Club, "Ask Twice, Listen, Be Kind"**, plus the Lighthouse Club YouTube channel and BuildingMentalHealth.net

## Key stats
- UK and Ireland: about 2 construction worker suicides every working day (roughly 500–700 a year; sources differ).
- UK male construction workers are about 4× more likely to die by suicide than the national average.
- US: a construction worker is 5× more likely to die by suicide than from all other workplace causes combined.

## Themes to cover in the product (from these sources and our interviews)
- Mood and depression signals: low mood, withdrawal, not talking to others
- Fatigue and sleep, which affect alertness and are a safety risk (matches our interviews)
- Low control over work, job insecurity and money stress
- Stigma: workers won't open up, so check-ins must be quick, anonymous and built on a "mates" peer culture
- Substance use
- Signposting to help: Lighthouse Club 24/7 helpline, Samaritans 116 123, Mates in Mind

## Short action clips for training (datasets)
- **Hugging Face egocentric trades sample**: 8 MP4 clips, first-person view, 1080p at 30 fps, about 4.7 GB in total; bricklaying, electrical, fabrication. https://huggingface.co/datasets/VerboseTechLabs/skilled-commercial-work-egocentric-sample
- **Zenodo assembly-line posture dataset**: unhealthy postures plus heart-rate and fatigue labels; 3 workers. https://zenodo.org/records/7043787
- **ConPPMF**: mental-fatigue dataset; 92 site video clips from 17 workers, plus smartwatch data and self-reported labels. No public download (try contacting the authors). https://hub.hku.hk/handle/10722/359564
- **11-activity construction worker dataset**: 500–1176 clips from real sites; described as public, but no download link found yet. https://bme.vgtu.lt/index.php/JCEM/article/download/6133/5711
- **VolvoConstAct (LS-HAR)**: 17 signalling actions, RGB, depth and skeleton data; availability unclear. https://arxiv.org/pdf/2410.01962
- **Proxy datasets for fatigue and drowsiness** (not construction): YawDD (yawning), DROZY
- **Fallback**: record our own 10–15 s clips on site, labelled e.g. normal / fatigued / unsafe posture

## Short clips: training and demo
### Training (fatigue)
- **NITYMED**: 107 yawning clips of 15–25 s plus 21 microsleep clips, mp4, 720p version about 700 MB (also on Kaggle). https://ieee-dataport.org/documents/nitymed
- **ZUT drowsiness set**: yawning, eye rubbing, head dropping. https://cvlab.zut.edu.pl/descriptions/1_drowsiness
- **YawDD**: normal / talking / yawning. https://site.uottawa.ca/~shervin/pubs/CogniVue-Dataset-ACM-MMSys2014.pdf
### Demo (construction stock clips; check licences)
- Mixkit "hard work" (free), incl. a construction worker on a hot day: https://mixkit.co/free-stock-video/hard-work/
- Videezy "Construction workers are relaxing" (4K): https://www.videezy.com/industry/4330-construction-workers-are-relaxing-4k-stock-video
- Videezy construction workers: https://www.videezy.com/free-video/bauarbeiter
- Pexels videos: search pexels.com/videos for "construction worker tired"
- Storyblocks "Tired and dirty construction worker" (paid): https://www.storyblocks.com/video/stock/tired-and-dirty-construction-worker-s4udaqfgbj2kqzpno

## More datasets (Kaggle, Hugging Face, Roboflow)
- **UTA-RLDD**: 60 people, 180 videos labelled alert / low-vigilance / drowsy (real, not acted); trim into 10–15 s clips. https://www.v7labs.com/open-datasets/uta-rldd
- **NTHU-DDD**: 36 subjects with acted yawning, slow blinking and falling asleep; AVI, 640x480. https://www.emergentmind.com/articles/nthu-ddd-dataset
- **Safe and unsafe behaviours** (Hugging Face, CC BY 4.0): 691 short videos in 8 classes, from a factory. https://docs.voxel51.com/dataset_zoo/datasets_hf/safe_and_unsafe_behaviours.html
- **Verbose Tech Labs trades sample** (also on Kaggle: kaggle.com/verbosetechlabsllp), CC BY 4.0
- **Roboflow Universe** (images, for detecting the worker / PPE before pose):
  - https://universe.roboflow.com/mohamed-8ior0/construction-site-workers
  - https://universe.roboflow.com/pose-nno5k/fall-ra4hm
- **LouisChen15/ConstructionSite** (Hugging Face, gated): construction-site safety rules. https://huggingface.co/datasets/LouisChen15/ConstructionSite

## Multi-site construction actions
- **CMA (Construction Meta Action)**: 1,595 clips from many YouTube construction sites, 7 worker-action classes (safe and unsafe). Download via Baidu Netdisk (link in the README). https://github.com/S1mpleyang/ConstructionActionRecognition
- Safe_and_Unsafe_Behaviours original: Mendeley https://data.mendeley.com/datasets/xjmtb22pff/1 (one factory in Eskişehir, Turkey)
