"""Attention Heads: the 51 people whose AI posts the site follows.

Only free, public sources are used:
  - Bluesky: the public API (no account, no key). A Bluesky handle is listed only when it is
    Bluesky-verified, on the person's own domain, or a profile whose description and follower
    count match the person (checked on 2026-10-11). Unknown or doubtful accounts are left out.
  - X: the X API is paid, so X posts are never fetched automatically. Paste a post link into
    state/heads_inbox.txt and the nightly run reads it through X's free embed service (oEmbed).

`known_for` is history, not a current job title, so it does not go stale.
An `id` that matches docs/data/people.json links the person to their People page.
"""

GROUPS = [
    {"id": "leaders", "label": "Lab leaders"},
    {"id": "researchers", "label": "Researchers"},
    {"id": "pioneers", "label": "Pioneers and teachers"},
    {"id": "builders", "label": "Builders"},
    {"id": "explainers", "label": "Explainers and critics"},
    {"id": "microsoft-data", "label": "Microsoft and data"},
]


def H(id, name, group, known_for, x, bsky=None, bsky_check=None):
    return {"id": id, "name": name, "group": group, "known_for": known_for,
            "x": x, "bsky": bsky, "bsky_check": bsky_check}


HEADS = [
    # Lab leaders
    H("sam-altman", "Sam Altman", "leaders", "Co-founded OpenAI and led the launch of ChatGPT", "sama"),
    H("dario-amodei", "Dario Amodei", "leaders", "Co-founded Anthropic, the maker of Claude", "DarioAmodei"),
    H("demis-hassabis", "Demis Hassabis", "leaders", "Co-founded DeepMind; AlphaGo, AlphaFold and a 2024 Nobel Prize", "demishassabis"),
    H("sundar-pichai", "Sundar Pichai", "leaders", "Led Google and Alphabet into the Gemini era", "sundarpichai"),
    H("satya-nadella", "Satya Nadella", "leaders", "Led Microsoft's bet on OpenAI and Copilot", "satyanadella"),
    H("mustafa-suleyman", "Mustafa Suleyman", "leaders", "Co-founded DeepMind and Inflection AI; wrote The Coming Wave",
      "mustafasuleyman", "mustafasuleymanai.bsky.social", "profile-match"),
    H("jensen-huang", "Jensen Huang", "leaders", "Co-founded NVIDIA, whose GPUs train most AI models", None),
    H("mark-zuckerberg", "Mark Zuckerberg", "leaders", "Founded Facebook; backs Meta's open Llama models", "finkd"),
    H("arthur-mensch", "Arthur Mensch", "leaders", "Co-founded Mistral AI", "arthurmensch",
      "arthurmensch.bsky.social", "profile-match"),
    H("aravind-srinivas", "Aravind Srinivas", "leaders", "Co-founded Perplexity", "AravSrinivas",
      "aravindsrinivas.bsky.social", "profile-match"),
    H("greg-brockman", "Greg Brockman", "leaders", "Co-founded OpenAI", "gdb"),
    H("ilya-sutskever", "Ilya Sutskever", "leaders", "Co-authored AlexNet; co-founded OpenAI and Safe Superintelligence", "ilyasut"),
    H("jack-clark", "Jack Clark", "leaders", "Co-founded Anthropic; writes the Import AI newsletter", "jackclarkSF"),
    # Researchers
    H("chris-olah", "Chris Olah", "researchers", "Pioneer of neural network interpretability; co-founded Anthropic", "ch402",
      "colah.bsky.social", "profile-match"),
    H("jan-leike", "Jan Leike", "researchers", "Alignment researcher; co-led OpenAI's Superalignment team", "janleike"),
    H("mark-chen", "Mark Chen", "researchers", "Led research at OpenAI; worked on Codex and DALL-E", "markchen90"),
    H("noam-brown", "Noam Brown", "researchers", "Built the poker AIs Libratus and Pluribus; reasoning research at OpenAI",
      "polynoamial", "polynoamial.bsky.social", "profile-match"),
    H("john-schulman", "John Schulman", "researchers", "Co-founded OpenAI; created the PPO training method", "johnschulman2"),
    H("jeff-dean", "Jeff Dean", "researchers", "Co-designed MapReduce and TensorFlow; long-time Google AI lead", "JeffDean",
      "jeffdean.bsky.social", "verified"),
    H("oriol-vinyals", "Oriol Vinyals", "researchers", "Co-authored sequence-to-sequence learning; led AlphaStar", "OriolVinyalsML"),
    H("lilian-weng", "Lilian Weng", "researchers", "Writes the Lil'Log explainers; co-founded Thinking Machines Lab", "lilianweng"),
    H("jason-wei", "Jason Wei", "researchers", "First author of the chain-of-thought prompting paper", "_jasonwei"),
    # Pioneers and teachers
    H("andrej-karpathy", "Andrej Karpathy", "pioneers", "Founding member of OpenAI; led Tesla Autopilot AI; coined vibe coding",
      "karpathy", "karpathy.bsky.social", "profile-match"),
    H("yann-lecun", "Yann LeCun", "pioneers", "Convolutional networks pioneer; 2018 Turing Award", "ylecun",
      "yann-lecun.bsky.social", "profile-match"),
    H("geoffrey-hinton", "Geoffrey Hinton", "pioneers", "Deep learning pioneer; 2018 Turing Award and 2024 Nobel Prize", "geoffreyhinton"),
    H("fei-fei-li", "Fei-Fei Li", "pioneers", "Created ImageNet; co-founded World Labs", "drfeifei",
      "drfeifei.bsky.social", "profile-match"),
    H("andrew-ng", "Andrew Ng", "pioneers", "Co-founded Google Brain and Coursera; teaches millions through DeepLearning.AI", "AndrewYNg"),
    H("francois-chollet", "François Chollet", "pioneers", "Created Keras and the ARC-AGI benchmark", "fchollet"),
    H("percy-liang", "Percy Liang", "pioneers", "Stanford professor behind the HELM benchmark and foundation model research", "percyliang"),
    # Builders
    H("peter-steinberger", "Peter Steinberger", "builders", "Founded PSPDFKit; created the OpenClaw personal agent", "steipete",
      "steipete.me", "own-domain"),
    H("boris-cherny", "Boris Cherny", "builders", "Created Claude Code at Anthropic", "bcherny",
      "bcherny.bsky.social", "verified"),
    H("logan-kilpatrick", "Logan Kilpatrick", "builders", "Product lead for Google AI Studio and the Gemini API", "OfficialLoganK"),
    H("kevin-weil", "Kevin Weil", "builders", "Led product at OpenAI", "kevinweil"),
    H("clem-delangue", "Clem Delangue", "builders", "Co-founded Hugging Face", "ClementDelangue",
      "clem.hf.co", "own-domain"),
    H("thomas-wolf", "Thomas Wolf", "builders", "Co-founded Hugging Face; led the Transformers library", "Thom_Wolf",
      "thomwolf.bsky.social", "profile-match"),
    H("harrison-chase", "Harrison Chase", "builders", "Created LangChain", "hwchase17"),
    H("jerry-liu", "Jerry Liu", "builders", "Created LlamaIndex", "jerryjliu0"),
    H("amjad-masad", "Amjad Masad", "builders", "Founded Replit", "amasad"),
    H("guillermo-rauch", "Guillermo Rauch", "builders", "Founded Vercel; created v0", "rauchg",
      "rauchg.blue", "own-domain"),
    H("jim-fan", "Jim Fan", "builders", "Robotics and embodied AI research at NVIDIA", "DrJimFan"),
    # Explainers and critics
    H("simon-willison", "Simon Willison", "explainers", "Co-created Django; builds Datasette and the llm tool; writes daily about AI",
      "simonw", "simonwillison.net", "verified"),
    H("ethan-mollick", "Ethan Mollick", "explainers", "Wharton professor; wrote Co-Intelligence", "emollick",
      "emollick.bsky.social", "verified"),
    H("swyx", "swyx", "explainers", "Popularised the term AI engineer; co-hosts Latent Space", "swyx",
      "swyx.io", "own-domain"),
    H("gary-marcus", "Gary Marcus", "explainers", "Cognitive scientist and AI's best-known sceptic", "GaryMarcus",
      "garymarcus.bsky.social", "verified"),
    H("arvind-narayanan", "Arvind Narayanan", "explainers", "Princeton professor; co-wrote AI Snake Oil", "random_walker",
      "randomwalker.bsky.social", "profile-match"),
    H("amanda-askell", "Amanda Askell", "explainers", "Philosopher who shapes Claude's character at Anthropic", "AmandaAskell"),
    H("nathan-lambert", "Nathan Lambert", "explainers", "RLHF researcher; writes Interconnects", "natolambert",
      "natolambert.bsky.social", "profile-match"),
    H("sebastian-raschka", "Sebastian Raschka", "explainers", "Wrote Build a Large Language Model (From Scratch)", "rasbt",
      "rasbt.bsky.social", "profile-match"),
    # Microsoft and data
    H("kevin-scott", "Kevin Scott", "microsoft-data", "Microsoft's CTO; a key voice on the OpenAI partnership", "kevin_scott"),
    H("amir-netz", "Amir Netz", "microsoft-data", "Microsoft Technical Fellow behind Power BI and Fabric", "AmirNetz"),
    H("marco-russo", "Marco Russo", "microsoft-data", "Co-founded SQLBI; the DAX and Power BI author", "marcorus",
      "marcorus.bsky.social", "profile-match"),
]
