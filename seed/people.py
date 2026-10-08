"""People who shape the field. Roles change, so each role carries an 'as of' date and a source.

The pipeline never edits a role. It tags news stories that mention a person (by
name or alias); a story like 'X joins Y' is flagged for a human to update the role.
`feeds` are the person's own channels; tools/check_feeds.py drops any that fail.
"""


def P(id, name, role, as_of, role_source, known_for, labs, concepts, aliases, feeds=(), links=()):
    return {"id": id, "name": name, "role": role, "role_as_of": as_of,
            "role_source": {"title": role_source[0], "url": role_source[1]},
            "known_for": known_for, "labs": list(labs), "concepts": list(concepts),
            "aliases": list(aliases), "feeds": [{"kind": f[0], "url": f[1]} for f in feeds],
            "links": [{"title": l[0], "url": l[1]} for l in links]}


PEOPLE = [
    P("sam-altman", "Sam Altman", "CEO, OpenAI", "2026-10",
      ("OpenAI announces leadership transition (and return)", "https://openai.com/index/openai-announces-leadership-transition/"),
      "Leads OpenAI through GPT-3, ChatGPT, GPT-4 and GPT-5, and sets much of the industry's pace.",
      ["openai"], ["llm", "agi", "chatbot"], ["Altman"],
      feeds=[("blog", "https://blog.samaltman.com/posts.atom")],
      links=[("Blog", "https://blog.samaltman.com/")]),
    P("dario-amodei", "Dario Amodei", "Co-founder and CEO, Anthropic", "2026-10",
      ("Introducing Claude", "https://www.anthropic.com/news/introducing-claude"),
      "Co-authored scaling laws and RLHF research at OpenAI, then co-founded Anthropic. Writes long essays on AI's future.",
      ["anthropic"], ["scaling-laws", "rlhf", "constitutional-ai", "ai-safety"], ["Amodei"],
      links=[("Essays", "https://darioamodei.com/")]),
    P("demis-hassabis", "Demis Hassabis", "Co-founder and CEO, Google DeepMind", "2026-10",
      ("The Nobel Prize in Chemistry 2024", "https://www.nobelprize.org/prizes/chemistry/2024/summary/"),
      "Led DeepMind to AlphaGo and AlphaFold; shared the 2024 Nobel Prize in Chemistry.",
      ["google"], ["reinforcement-learning", "deep-learning", "agi"], ["Hassabis"],
      links=[("Google DeepMind", "https://deepmind.google/")]),
    P("andrew-ng", "Andrew Ng", "Founder, DeepLearning.AI", "2026-10",
      ("DeepLearning.AI", "https://www.deeplearning.ai/"),
      "Co-founded Google Brain and Coursera, and taught machine learning to millions. Writes The Batch newsletter.",
      ["google", "academia"], ["deep-learning", "gpu", "agent"], ["Andrew Ng"],
      links=[("The Batch", "https://www.deeplearning.ai/the-batch/")]),
    P("andrej-karpathy", "Andrej Karpathy", "Pretraining team, Anthropic (reported May 2026)", "2026-05",
      ("exchange4media: Andrej Karpathy joins Anthropic", "https://www.exchange4media.com/people-movement-news/andrej-karpathy-joins-anthropic-154782.html"),
      "OpenAI founding member and former Tesla AI director. The best-known explainer of how LLMs work; coined 'vibe coding'.",
      ["anthropic", "openai"], ["llm", "pretraining", "vibe-coding"], ["Karpathy"],
      feeds=[("blog", "https://karpathy.bearblog.dev/feed/")],
      links=[("Blog", "https://karpathy.bearblog.dev/"), ("GitHub", "https://github.com/karpathy")]),
    P("geoffrey-hinton", "Geoffrey Hinton", "Professor emeritus, University of Toronto", "2026-10",
      ("The Nobel Prize in Physics 2024", "https://www.nobelprize.org/prizes/physics/2024/summary/"),
      "Backpropagation, deep belief nets and AlexNet. Left Google in 2023 to speak freely about AI risk; 2024 Nobel Prize in Physics.",
      ["academia"], ["backpropagation", "deep-learning", "ai-safety"], ["Hinton"]),
    P("yann-lecun", "Yann LeCun", "Founder of a new AI startup after leaving Meta (2026)", "2026-10",
      ("Bloomberg Law: LeCun's new AI startup raises $1 billion seed",
       "https://news.bloomberglaw.com/private-equity/yann-lecuns-new-ai-startup-raises-1-billion-in-seed-funding"),
      "Pioneer of convolutional networks, long-time Meta chief AI scientist, and advocate of world models and open research.",
      ["meta", "academia"], ["cnn", "world-model", "open-weight-model"], ["LeCun"]),
    P("ilya-sutskever", "Ilya Sutskever", "Co-founder, Safe Superintelligence (SSI)", "2026-10",
      ("Safe Superintelligence Inc.", "https://ssi.inc/"),
      "Co-author of AlexNet and sequence-to-sequence learning, OpenAI co-founder and chief scientist, now building SSI.",
      ["ssi", "openai"], ["deep-learning", "ai-safety", "agi"], ["Sutskever"]),
    P("fei-fei-li", "Fei-Fei Li", "Co-founder and CEO, World Labs", "2026-10",
      ("World Labs", "https://www.worldlabs.ai/"),
      "Created ImageNet, co-directs Stanford's Human-Centered AI institute, and works on spatial intelligence.",
      ["academia", "other"], ["dataset", "world-model"], ["Fei-Fei Li"]),
    P("peter-steinberger", "Peter Steinberger", "OpenAI (personal agents), creator of OpenClaw", "2026-02",
      ("Fortune: Who is Peter Steinberger",
       "https://fortune.com/2026/02/19/openclaw-who-is-peter-steinberger-openai-sam-altman-anthropic-moltbook"),
      "Built the viral open-source personal agent OpenClaw, then joined OpenAI to work on personal agents.",
      ["openai", "other"], ["personal-agent", "agent"], ["Steinberger", "steipete", "OpenClaw"],
      feeds=[("blog", "https://steipete.me/rss.xml")],
      links=[("Blog", "https://steipete.me/"), ("GitHub", "https://github.com/steipete")]),
]
