"""Analysis logic for GitHub user contributions."""

import re
from collections import Counter
from typing import Any

STOP_WORDS: set[str] = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "can",
    "had",
    "her",
    "was",
    "one",
    "our",
    "out",
    "day",
    "get",
    "has",
    "him",
    "his",
    "how",
    "man",
    "new",
    "now",
    "old",
    "see",
    "two",
    "way",
    "who",
    "boy",
    "did",
    "its",
    "let",
    "put",
    "say",
    "she",
    "too",
    "use",
    "fix",
    "add",
    "update",
    "merge",
    "commit",
    "pr",
    "pull",
    "request",
    "change",
    "changes",
    "branch",
    "into",
    "from",
    "review",
    "more",
    "some",
    "time",
    "very",
    "what",
    "know",
    "just",
    "first",
    "also",
    "after",
    "back",
    "other",
    "many",
    "than",
    "only",
    "those",
    "come",
    "make",
    "well",
    "over",
    "think",
    "where",
    "being",
    "each",
    "made",
    "most",
    "could",
    "state",
    "want",
    "because",
    "before",
    "good",
    "much",
    "year",
    "work",
    "take",
    "these",
    "them",
    "there",
    "their",
    "would",
    "should",
    "have",
    "this",
    "that",
    "with",
    "they",
    "been",
    "were",
    "said",
    "which",
    "will",
    "about",
    "if",
    "then",
    "so",
    "up",
    "by",
    "on",
    "at",
    "to",
    "of",
    "in",
    "is",
    "it",
    "a",
    "an",
    "as",
    "or",
    "be",
    "we",
    "he",
    "my",
    "me",
    "i",
    "z",
    "w",
    "na",
    "do",
    "dla",
    "oraz",
    "się",
    "nie",
    "jest",
    "są",
    "tego",
    "tylko",
    "lub",
    "ale",
    "za",
    "od",
    "po",
    "przez",
    "kto",
    "co",
    "gdzie",
    "kiedy",
    "jak",
    "ze",
    "pod",
    "nad",
    "przy",
    "jako",
    "aby",
    "żeby",
    "ten",
    "ta",
}


def _is_excluded(repo_owner: str, excluded_owner: str | None) -> bool:
    if not excluded_owner:
        return False
    return repo_owner.strip().lower() == excluded_owner.strip().lower()


def _extract_terms(texts: list[str], top_n: int = 7) -> list[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for word in re.findall(r"\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{3,}\b", text):
            word_lower = word.lower()
            if word_lower not in STOP_WORDS:
                counter[word_lower] += 1
    return [term for term, _ in counter.most_common(top_n)]


def analyze_contributions(
    raw_data: dict[str, Any],
    excluded_owner: str | None = None,
    target_org: str | None = None,
) -> dict[str, Any]:
    """
    Filter and summarize contributions.
    - excluded_owner: if provided, contributions from this owner are omitted.
    - target_org: if provided, only contributions matching this owner/organization are kept.
    """
    target_org_normalized = target_org.strip().lower() if target_org and target_org.strip() else None

    def _matches_filters(owner: str) -> bool:
        owner_clean = owner.strip()
        if _is_excluded(owner_clean, excluded_owner):
            return False
        return not (target_org_normalized and owner_clean.lower() != target_org_normalized)

    commit_repos = [r for r in raw_data.get("commit_contributions_by_repo", []) if _matches_filters(r.get("owner", ""))]
    pr_repos = [r for r in raw_data.get("pr_contributions_by_repo", []) if _matches_filters(r.get("owner", ""))]
    commits = [c for c in raw_data.get("commits", []) if _matches_filters(c.get("owner", ""))]
    prs = [p for p in raw_data.get("pull_requests", []) if _matches_filters(p.get("owner", ""))]

    repo_names = sorted(
        {r["name_with_owner"] for r in commit_repos + pr_repos if "name_with_owner" in r}
        | {c["repo_name_with_owner"] for c in commits if "repo_name_with_owner" in c}
        | {p["repo_name_with_owner"] for p in prs if "repo_name_with_owner" in p}
    )

    total_commits = sum(r.get("commit_count", 0) for r in commit_repos)
    total_prs = sum(r.get("pr_count", 0) for r in pr_repos)

    languages: Counter[str] = Counter()
    for r in commit_repos:
        lang = r.get("primary_language")
        if lang:
            languages[lang] += r.get("commit_count", 0)
    for r in pr_repos:
        lang = r.get("primary_language")
        if lang:
            languages[lang] += r.get("pr_count", 0)

    main_languages = [lang for lang, _ in languages.most_common(5)]
    text_sources = [c["message"] for c in commits if c.get("message")] + [p["title"] for p in prs if p.get("title")]
    top_terms = _extract_terms(text_sources, 7)

    main_areas = list(dict.fromkeys(main_languages + top_terms))

    top_work: list[str] = []
    for pr in prs[:10]:
        top_work.append(f"- [{pr.get('repo_name_with_owner', '')}] {pr.get('title', '')}")
    for c in commits[:10]:
        if len(top_work) >= 10:
            break
        headline = c.get("headline") or (c.get("message", "").splitlines()[0] if c.get("message") else "")
        top_work.append(f"- [{c.get('repo_name_with_owner', '')}] {headline}")

    what_learned: list[str] = []
    for lang in main_languages:
        what_learned.append(f"- {lang}")
    for term in top_terms[:5]:
        what_learned.append(f"- {term}")

    projects: list[dict[str, Any]] = []
    for name in repo_names:
        c_count = next((r.get("commit_count", 0) for r in commit_repos if r.get("name_with_owner") == name), 0)
        p_count = next((r.get("pr_count", 0) for r in pr_repos if r.get("name_with_owner") == name), 0)
        lang = next(
            (r.get("primary_language") for r in commit_repos + pr_repos if r.get("name_with_owner") == name), None
        )
        projects.append(
            {
                "name": name,
                "commits": c_count,
                "prs": p_count,
                "language": lang,
            }
        )

    return {
        "user": raw_data.get("user", ""),
        "month": raw_data.get("month", ""),
        "repositories": repo_names,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "projects": projects,
        "main_areas": main_areas,
        "top_work": top_work,
        "what_learned": what_learned,
        "raw_data": raw_data,
    }
