"""Synthetic course text for calibrating topic links (never real course material).

Each topic has passages that teach it, and the passages of the other topics are the
negatives. The real-model test checks the configured threshold separates them.
"""

TOPICS: dict[str, tuple[str, list[str]]] = {
    "Microservices": (
        "Splitting an application into small services that are deployed independently.",
        [
            "A microservice architecture structures an application as a collection of small, "
            "loosely coupled services. Each service owns its data and can be deployed on its own.",
            "Teams can release one service without redeploying the whole system, because "
            "services communicate over well-defined APIs such as REST or messaging.",
        ],
    ),
    "Password storage": (
        "Storing passwords safely with salts and slow hash functions such as bcrypt.",
        [
            "Never store plain-text passwords. Add a random salt to each password and hash it "
            "with a slow function like bcrypt, scrypt or Argon2.",
            "A salt defeats precomputed rainbow tables, and a work factor makes brute-forcing "
            "each stolen hash expensive.",
        ],
    ),
    "Normalisation": (
        "Organising relational tables into normal forms to remove redundancy.",
        [
            "First normal form requires atomic values; second normal form removes partial "
            "dependencies on a composite key.",
            "Third normal form removes transitive dependencies, so every non-key attribute "
            "depends on the key, the whole key and nothing but the key.",
        ],
    ),
    "Process scheduling": (
        "How an operating system decides which process runs next on the CPU.",
        [
            "Round-robin scheduling gives each ready process a fixed time quantum before it is "
            "pre-empted and moved to the back of the ready queue.",
            "Shortest-job-first minimises average waiting time but can starve long processes; "
            "priority aging prevents starvation.",
        ],
    ),
}

# Course admin text that should link to none of the topics.
UNRELATED = [
    "The semester test will be written in the main hall. Bring your student card.",
    "Office hours are on Tuesdays from 14:00 to 15:00 in room 4-12.",
]
