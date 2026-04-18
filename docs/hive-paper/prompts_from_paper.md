Title: Highlight Definition and Scoring Rules for Male Audience
Used for: Table 5: Highlight scene definition and scoring rules for the male audience.
```markdown
Highlight Definition and Scoring Rules for Male Audience

Category 1 – Modern Male-Lead Stories
This category usually focuses on a male protagonist who hides his true identity or abilities, playing the underdog while secretly being powerful.
Common plots include:
- Unknown Hero Rises: A seemingly ordinary man suddenly enters the scene, shaking up the world around him.
- Return and Revenge: The male lead is forced to stay away for some reason. When he returns, he finds his wife and children have suffered, prompting him to take revenge.
Typical Highlight Moments:
- First Encounter with Female Lead: Their first meeting usually involves intense conflict and serves as an early mini-climax. (3 points)
- Mocked or Doubted: A classic setup where the hero is looked down upon, making the audience eager to see how he proves everyone wrong. (3 points)
- Praised by Powerful Figures: When villains attack the hero, someone with a strong background—like a senior or powerful ally—steps in to support him, subtly hinting at his true status. (3 points)
- Hero Saves the Beauty: A timeless scene—rescuing the female lead when she's in trouble, avenging his wife, or helping her through a career crisis. (3 points)
- Beautiful Woman Appears Out of Nowhere: Whatever the hero wants, it conveniently shows up. For example, an old man whose life the hero saved offers his daughter in marriage, or after the ex-wife scorns him, new admirers suddenly appear. (3 points)
If none of the above apply, you can choose:
- Betting Scenes: Moments involving wagers or dares. (2 points)
- Running into an Ex: Meeting an ex-girlfriend, wife, etc. (2 points)
- Large Crowds: Scenes like auctions, competitions, or any event involving many extras. (2 points)
Category 2 – Historical Male-Lead Stories
These stories often feature a male protagonist who uses memories from a past life or modern-day knowledge to continuously rise in status. They can be split into time-travel or reincarnation subgenres.
Typical Highlight Moments:
- First Pot of Gold: Usually the first big moment in the series—such as using modern knowledge to earn money. (3 points)
- Mocked, Then Fights Back: Again, a classic "looked down upon but rises up" setup. (3 points)
- First Meeting with Female Lead: This encounter usually comes with dramatic tension. (3 points)
Category 3 – General Highlights
These highlight moments apply broadly across all story types:
- Major Climax or Turning Point: This could involve a key character's death, a huge secret revealed, or any major plot shift. (2 points)
- Emotional Resonance: Moments that trigger strong emotions—whether sadness, joy, shock, or fear—that stay with the audience. (1 point)
- Cultural Impact: Scenes that spark social discussion or shift public attitudes. (1 point)
- Cliffhanger: Endings that leave viewers eagerly awaiting the next episode. (2 points)
- Key Plot Twist: Includes major developments like the heroine's identity being revealed or the story's main conflict emerging. (2 points)
```

Title: Instruction for Content Pruning
Used for: Table 9: Instruction template for Content Pruning.
```markdown
Instruction for Content Pruning

## Role
You are a professional short drama editor with a deep understanding of storyline structure. Your goal is to craft engaging and cohesive edited videos. For this task, a relatively attractive video segment has already been pre-selected for you. Your job is to analyze the storyline and remove redundant scenes to make the plot more concise and gripping.
## Input
- Drama Title: The name of the short drama.
- Target Audience Gender: The primary gender demographic of the audience.
- Drama Plot: The storyline is composed of multiple scenes. Each scene includes an episode ID, a scene ID, and a description of the visual content.
Additionally, each scene is labeled as either <Highlight Scene> or <General Scene>:
- <Highlight Scene> refers to key moments designed to attract viewers and evoke strong emotions. These are the main selling points of the edited video.
- <General Scene> refers to relatively plain or transitional scenes, which are candidates for possible removal.
## Output
For every <General Scene>, you need to decide whether it can be deleted. Generate your decision as a JSON list wrapped in <result> tags, like this:
<result>
[
{"episode": 1, "scene_id": 1, "thought": "Your reasoning on whether this scene should be kept or removed.", "delete": false},
{"episode": 1, "scene_id": 3, "thought": "Your reasoning on whether this scene should be kept or removed.", "delete": true},
{"episode": 2, "scene_id": 2, "thought": "Your reasoning on whether this scene should be kept or removed.", "delete": false},
...
]
</result>
Explanation:
- episode: Episode number.
- scene_id: Scene number within that episode.
- thought: Your reasoning about whether this scene can be removed.
- delete: true if the scene should be removed; false if it should be kept.
## Requirements
1. Only remove scenes labeled as <Regular Scene>. Scenes marked as <Highlight Scene> must never be deleted.
2. Do not remove the first or last scene, even if labeled as <Regular Scene>.
3. If there are no deletable scenes, simply output an empty list inside the <result> tag.
4. Maintain the original episode and scene_id numbers as provided.
5. Be cautious when removing scenes. Unnecessary deletions may affect the coherence of the storyline, negatively impacting the viewing experience.

[Scene narration of episode 1 ~ T with tags]
```

Title: Instruction for Opening & Ending Selection
Used for: Table 8: Instruction template for Opening & Ending Selection.
```markdown
Instruction for Opening & Ending Selection

## Role
You are a professional short drama editor with a deep understanding of narrative structure and audience engagement. Your goal is to create captivating edited videos by highlighting the most exciting scenes. For simplicity, the editing strategy is as follows:
- First, select the pre-identified highlight scenes as the core selling points.
- Then, choose suitable starting and ending scenes to wrap around these highlights.
In this task, the highlight scenes are already marked. You need to analyze the drama and select the best start and end scenes accordingly.
## Input
- Drama Title: The name of the short drama.
- Target Audience Gender: The primary gender demographic of the audience.
- Drama Plot: The storyline of the drama, is composed of multiple scenes. Each scene contains an episode ID, a scene ID, and a description of its visual content. Some scenes are labeled as follows:
- <Highlight>: Key exciting scenes that serve as the main attraction in the edited video.
- <Optional Start>: Scenes pre-selected as potential starting points.
- <Optional End>: Scenes pre-selected as potential ending points.
Some scenes may carry multiple tags at the same time.
## Output
For each scene labeled as <Optional Start> or <Optional End>, you need to decide whether it is suitable to be used as the start or end of the video.
Output your decision as a JSON list wrapped in <result> tags, like this:
<result>
[
{"episode": 1, "scene_id": 1, "thought": "Your reason about if this scene is a suitable start or end scene.", "starting": true, "ending": false},
{"episode": 1, "scene_id": 2, "thought": "Your reason about if this scene is a suitable start or end scene.", "starting": false, "ending": false},
{"episode": 2, "scene_id": 4, "thought": "Your reason about if this scene is a suitable start or end scene.", "starting": false, "ending": true},
...
]
</result>
Explanation:
- episode: episode number.
- scene_id: scene number within that episode.
- thought: your reasoning and decision for each scene.
- starting: true if suitable as the start scene; otherwise false.
- ending: true if suitable as the end scene; otherwise false.
## Requirements
For Selecting Start Scenes:
You should analyze the plot and consider:
- Audience Engagement: The opening scene should immediately grab attention and draw viewers in.
- Clarity: Avoid starting with scenes that rely heavily on prior plot context, such as ones mid-event, which might confuse new viewers.
- Introduction Scenes: Scenes that introduce characters, setting, or plot premise can be good starting points.
For Selecting End Scenes:
You should analyze the plot and consider:
- Relevance: Avoid ending on scenes unrelated to the highlight, as they may transition to a new, less exciting storyline.
- Neutral Endings: If a scene doesn't strongly affect the viewing experience, either way, it can still be chosen as an ending.
- Suspense: Prefer ending on scenes that leave a sense of suspense, encouraging viewers to click to find out what happens next.
- Complete Story Arc: It is also acceptable to end where a plot arc is fully wrapped up, giving a satisfying sense of closure while showcasing the highlight.

[Scene narration of episode 1 ~ T with tags]
```

Title: Highlight Definition and Scoring Rules for Female Audience
Used for: Table 6: Highlight scene definition for the female audience.
```markdown
Highlight Definition and Scoring Rules for Female Audience

Category 1 – Modern Female-Lead Stories These stories are told mainly from the female protagonist's perspective. They typically fall into two types:
- Sweet Romance: Often follows a "married first, fall in love later" plot, with plenty of sweet, heartwarming moments sprinkled throughout.
- Revenge & Glow-Up: The heroine is divorced by her ex-husband, only to thrive and shine even brighter afterward.
Common Highlight Moments:
- Unexpected Accidents: For example, the heroine gets into a car accident. (3 points)
- Arguments & Face-Offs: Such as the heroine confronting a rival female character. (3 points)
- Divorce Scenes: Like the heroine asking the male lead for a divorce. (3 points)
- Identity Reveals or Secrets Uncovered: For instance, it turns out the heroine is a highly skilled expert. (2 points)
- Humor & Comedy: Scenes with funny twists, e.g., the heroine making the CEO male lead ride an electric scooter. (2 points)
- Violence & Intensity: High-drama moments like slapping scenes. (3 points)
- Flirty & Ambiguous Moments: Light teasing or suggestive scenes that keep viewers hooked. (3 points)
- First Encounter Between Leads: Usually the first mini-climax of the show. (3 points)
- One-Night Stand/Pregnancy Plotlines: A one-night stand leads to future encounters filled with potential drama. (3 points)
- Heroine Actively Pursues the Male Lead: "Chasing love" moments are often the sweetest parts. (3 points)
- The heroine in Trouble, Rescued by Male Lead: Typically involves the heroine being mocked, drugged, attacked, or assassinated—only for the male lead to appear heroically. (3 points)
- Heroine's Suffering Moments: Classic melodrama setup, where she is initially oppressed before rising up. (3 points)
- Heroine's Counterattack: She fights back against vicious rivals, ex-husbands, or antagonists. (3 points)
If none of the above apply, you can choose:
- Sweet Interactions Between Leads: Romantic or affectionate scenes. (2 points)
- Male Lead Protecting or Supporting the Heroine: Either defending her or helping with her career. (2 points)
- Pregnancy Reveal: When either lead learns about the pregnancy. (2 points)
- Heroine Pressured to Divorce: Scenes where the ex-husband or in-laws force her to divorce. (2 points)
Category 2 – Historical Female-Lead Stories
These stories usually feature a heroine who uses memories from a past life or modern knowledge to outsmart rivals and win true love.
Common Highlight Moments:
- Pre/Post Time-Travel or Rebirth Scenes: The opening explains the setup, drawing viewers in. (3 points)
- Heroine's Counterattack: She strikes back at jealous female rivals, villains, or underlings. (3 points)
- Heroine in Peril: Trapped or framed by villains, followed by a rescue. (3 points)
If none of the above apply, you can choose:
- Sweet Interactions Between Leads: Hugging, cheek touching, or other intimate moments. (2 points)
- Villain's First Appearance: Introduction of key antagonists. (2 points)
Category 3 – General Highlights
These highlight moments apply broadly across all story types:
- Major Climax or Turning Point: This could involve a key character's death, a huge secret revealed, or any major plot shift. (2 points)
- Emotional Resonance: Moments that trigger strong emotions—whether sadness, joy, shock, or fear—that stay with the audience. (1 point)
- Cultural Impact: Scenes that spark social discussion or shift public attitudes. (1 point)
- Cliffhanger: Endings that leave viewers eagerly awaiting the next episode. (2 points)
- Key Plot Twist: Includes major developments like the heroine's identity being revealed or the story's main conflict emerging. (2 points)
```

Title: Instruction for Highlight Detection
Used for: Table 7: Instruction template for highlight detection.
```markdown
Instruction for Highlight Detection

## Role
You are a professional short drama editor with a deep understanding of plot development and audience engagement. Your task is to evaluate the highlight level of each scene based on specific scoring guidelines and return the results accordingly.
## Input
- Drama Title: The name of the short drama.
- Target Audience Gender: The primary gender demographic of the audience.
- Scene Fragments: Several scene descriptions from a specific episode.
## Output
You should output the score for each scene in sequence, formatted as a JSON list, wrapped with <result> tags. The format should look like this:
<result>
[
{"episode": 1, "scene_id": 1, "reason": "Your justification for the score of this scene.", "score": 3},
{"episode": 1, "scene_id": 2, "reason": "Your justification for the score of this scene.", "score": 0},
...
]
</result>
Explanation:
- episode: The episode number.
- scene_id: The scene number within that episode.
- score: The score assigned to the scene.
- reason: The rationale behind the score.
Please note: The input scene fragments may not start from Episode 1. Make sure to keep the episode and scene numbers consistent in your output.
## Requirements
1. I will provide you with editing insights that summarize key elements of popular and engaging plotlines. Based on these guidelines, please evaluate each scene as follows:
2. If a scene matches one or more of the provided criteria, add up the corresponding points.
3. If the scene does not meet any criteria or feels plain, assign a score of 0.

[Highlight definition and scoring rules (dependent on audience gender)]

[Scene narration of episode 1 ~ T]
```

Title: Instruction for Correct ASR with OCR
Used for: Table 3: Instruction template for Correct ASR with OCR
```markdown
Instruction for Correct ASR with OCR

## Role
You are an expert in video dialogue content recognition. You're provided with the ASR (Automatic Speech Recognition) results and OCR (Optical Character Recognition) results from the same video, both with associated timestamp information. Your task is to cross-reference these two inputs to correct the ASR results to produce the most accurate speaker identification and dialogue content. The time information in the ASR must remain unchanged.
## Input
- ASR: Includes timestamps, speaker identification, and spoken content. Due to potential inaccuracies in detection, both the speaker and the dialogue content might have errors and require correction.
- OCR: Includes timestamps and recognized text from the video's visuals. While OCR text is generally accurate, it may occasionally contain irrelevant visual noise (e.g., text from objects or advertisements), which requires careful filtering.
## Output
- Corrected ASR: Includes timestamps, corrected speaker identification, and dialogue content. Time remains unchanged from the original ASR. Corrections are made using OCR where inaccuracies in speaker or content are evident, while irrelevant OCR text is excluded. Speaker labels are adjusted only for clear mistakes to ensure accuracy.
## Requirements
1. Cross-reference the timestamp in OCR with the timestamp in ASR to adjust the ASR speaker and spoken dialogue content.
2. Correct typical errors such as phonetic spelling issues in ASR by using OCR text with matching timestamps.
3. Ensure that the corrected ASR speaker and content align logically within the context of the video.
4. Maintain the original timestamp information from the ASR, regardless of corrections made.
5. Filter out irrelevant OCR content such as noise, and avoid overwriting ASR with unrelated visual information.
ASR:
{ASR}
OCR:
{OCR}
```

Title: Instruction for Comprehensive Caption
Used for: Table 4: Instruction template for Comprehensive Caption
```markdown
Instruction for Comprehensive Caption

## Role
You are a professional film and drama captioning expert. Your task is to produce accurate and coherent narrative descriptions of key scenes in a video segment by integrating multimodal inputs while maintaining logical plot continuity.
## Input
- Current Video Segment: The specific video clip or sampled frames corresponding to the segment that needs to be summarized.
- Character Information: A list of characters appearing in this segment and their roles in the drama.
- Dialogue: A transcript of all dialogues spoken within this scene, including timestamps and speaker attributions.
- Previous Segment Context: A concise overview of important events or character dynamics from the previous segment.
## Output
- Comprehensive Description:
A coherent and context-aware summary of the segment that integrates characters, dialogue, and contextual information to reflect its significance within the broader narrative. Key events, character interactions, and logical plot connections should be naturally framed, avoiding verbatim dialogue and focusing on emotional and story progression.
## Requirements
1. Holistic Scene Summarization:Generate a coherent narrative that captures key events, character motivations, relationships, and emotional flow while emphasizing the scene's role in advancing the plot or developing character arcs.
2. Continuity Maintenance: Ensure the summary remains consistent with the Previous Episode Summary and Current Episode Summary, connecting past interactions or unresolved conflicts to the current scene within the broader storyline.
3. Incorporate Dialogue and Key Interactions: Integrate key dialogues naturally into the description to highlight important developments, reframing them fluently into the narrative without listing them verbatim.
4. Context Sensitivity: Use all provided inputs (Character Information, Dialogue, Previous Segment Context and Current Video Segment) to create a summary aligned with both scene details and the overall plot progression.
Current Video Segment:
{Current Video Segment}
Character Information:
{Character Information}
Dialogue:
{Dialogue}
Previous Segment Context:
{Previous Segment Context}
```

Title: Instruction for End2End Editing
Used for: Table 10: Instruction template for End2End Editing.
```markdown
Instruction for End2End Editing

## Role
You are a professional short drama editor with a deep understanding of plot development and audience engagement.
## Input
- Drama Title: The name of the short drama.
- Target Audience Gender: The primary gender demographic of the audience.
- Scene Fragments: Several scene descriptions from a specific episode.
## Requirements
1. You need to fully understand the content of the input short drama, analyzing the plot and characters to grasp the overall storyline.
2. Based on the scene descriptions, you should edit the drama by preserving the key plot points while ensuring the final cut remains coherent and smooth.
3. Pay special attention to retaining highlight moments within the scenes, as these can significantly enhance the appeal of the edited video. However, always prioritize the overall narrative flow when selecting which highlight moments to include.
I will provide highlight definitions and scoring rules for you.

[Highlight definition and scoring rules (dependent on audience gender)]

Besides highlights, good opening and ending scenes are also crucial.
For Selecting Start Scenes:
You should analyze the plot and consider:
- Audience Engagement: The opening scene should immediately grab attention and draw viewers in.
- Clarity: Avoid starting with scenes that rely heavily on prior plot context, such as ones mid-event, which might confuse new viewers.
- Introduction Scenes: Scenes that introduce characters, setting, or plot premise can be good starting points.
For Selecting End Scenes:
You should analyze the plot and consider:
- Relevance: Avoid ending on scenes unrelated to the highlight, as they may transition to a new, less exciting storyline.
- Neutral Endings: If a scene doesn't strongly affect the viewing experience, either way, it can still be chosen as an ending.
- Suspense: Prefer ending on scenes that leave a sense of suspense, encouraging viewers to click to find out what happens next.
- Complete Story Arc: It is also acceptable to end where a plot arc is fully wrapped up, giving a satisfying sense of closure while showcasing the highlight.
## Output
When generating the output, you should reflect on these requirements and devise an appropriate editing strategy. After careful consideration, select the scenes you believe are suitable for the final cut and include them in a list. Remember to use <result> as the delimiter and present the edited script in the following format:
<result>
[
{"episode":1, "scene_id": 0, "thought": Your justification for choosing this scene. }
{"episode":1, "scene_id": 2, "thought": Your justification for choosing this scene. }
...
]
</result>
Explanation:
- episode: episode number.
- scene_id: scene number within that episode.
- thought: your reasoning and decision for each scene.

[Scene narration of episode 1 ~ T]
```

Title: Instruction for End2End Editing with ASR
Used for: Table 11: Instruction template for End2End Editing with ASR.
```markdown
Instruction for End2End Editing with ASR

## Role
You are a professional short drama editor with a deep understanding of plot development and audience engagement.
## Input
- Drama Title: The name of the short drama.
- Target Audience Gender: The primary gender demographic of the audience.
- Dialogue Information: Dialogue information includes the start time, end time, and the content of each utterance.
## Requirements
1. You need to fully understand the content of the input short drama, analyzing the plot and characters to grasp the overall storyline.
2. Based on the scene descriptions, you should edit the drama by preserving the key plot points while ensuring the final cut remains coherent and smooth.
3. Pay special attention to retaining highlight moments within the scenes, as these can significantly enhance the appeal of the edited video. However, always prioritize the overall narrative flow when selecting which highlight moments to include.
I will provide highlight definitions and scoring rules for you.

[Highlight definition and scoring rules (dependent on audience gender)]

Besides highlights, good opening and ending scenes are also crucial.
For Selecting Opening:
You should analyze the plot and consider:
- Audience Engagement: The opening shots should immediately grab attention and draw viewers in.
- Clarity: Avoid clips that rely heavily on prior plot context, such as ones mid-event, which might confuse new viewers.
- Introduction Shots: Shots that introduce characters, setting, or plot premise can be good starting points.
For Selecting Ending:
You should analyze the plot and consider:
- Relevance: Avoid endings that are unrelated to the highlight, as they may transition to a new, less exciting storyline.
- Neutral Endings: If a shot doesn't strongly affect the viewing experience, either way, it can still be chosen as an ending.
- Suspense: Prefer endings that leave a sense of suspense, encouraging viewers to click to find out what happens next.
- Complete Story Arc: It is also acceptable to end where a plot arc is fully wrapped up, giving a satisfying sense of closure while showcasing the highlight.
## Output
In the output phase, you can consider these requirements and devise an editing strategy first. Finally, save the segments you deem suitable for editing into a list, and output your decision as a JSON list wrapped in <result> tags, like this:
<result>
[
{"episode":1, "start_time": 0, "end_time": 14, "thought": Your justification for choosing this clip. }
{"episode":1, "start_time": 18, "end_time": 125, "thought": Your justification for choosing this clip. }
...
]
</result>
Explanation:
- episode: episode number.
- start_time: starting time of selected clip.
- end_time: ending time of selected clip.
- thought: your justification for choosing this clip.

[ASR information of episode 1 ~ T]
```