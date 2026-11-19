"""Search eval: ``uv run --directory apps/api python -m evals.search cos330``.

Runs each query in ``evals/search/<name>.yaml`` through ``search_module`` (the service the
API uses, with the real local embedder), and prints the rank of the first acceptable
page and of the first acceptable slide. Results are ranked as the API returns them: one
row per chunk, 20 at most.

Pass: any acceptable page in the top 3 for at least 12 of 15 queries (exit code 0).

``--retrieval`` runs the tutor's retrieval instead (``evals/search/retrieval.py``).
"""

import asyncio
import sys

from app.services.search.embedding import get_embedder
from app.services.search.search import search_module
from evals.common import dev_session, find_module, load_config
from evals.metrics import Page, first_rank, in_top, mean_reciprocal_rank
from evals.search import retrieval

LIMIT = 20
TOP = 3
PASS_AT_LEAST = 12


def show(rank: int | None) -> str:
    return f"{rank:>2}" if rank is not None else " -"


async def main(name: str) -> int:
    config = load_config(f"search/{name}.yaml")
    queries = config["queries"]
    embedder = await asyncio.to_thread(get_embedder)
    any_ranks: list[int | None] = []
    slide_ranks: list[int | None] = []
    async with dev_session() as session:
        module_id, user_id = await find_module(session, config["module"])
        print(f"Search eval: {config['module']}, {len(queries)} queries, top {LIMIT} results each")
        print(" #  any  slide  query")
        for number, item in enumerate(queries, start=1):
            found = await search_module(
                session, module_id, item["query"], user_id=user_id, embedder=embedder, limit=LIMIT
            )
            results: list[Page] = [(hit.material_title, hit.page_number) for hit in found.hits]
            pages = {(p["material"], int(p["page"])) for p in item["pages"]}
            slides = {(p["material"], int(p["page"])) for p in item["pages"] if p["slide"]}
            any_rank, slide_rank = first_rank(results, pages), first_rank(results, slides)
            any_ranks.append(any_rank)
            slide_ranks.append(slide_rank)
            top = results[0] if results else None
            note = ""
            if slide_rank is None or slide_rank > TOP:
                note = f"   (first: {top[0]} p{top[1]})" if top else "   (no results)"
            print(f"{number:>2}   {show(any_rank)}     {show(slide_rank)}  {item['query']}{note}")

    total = len(queries)
    slide_top, any_top = in_top(slide_ranks, TOP), in_top(any_ranks, TOP)
    print()
    print(f"Slide in the top {TOP}:          {slide_top}/{total}  (ROADMAP criterion: 12)")
    print(f"Any acceptable page in top {TOP}: {any_top}/{total}")
    print(f"MRR (any acceptable page):    {mean_reciprocal_rank(any_ranks):.3f}")
    passed = any_top >= PASS_AT_LEAST
    print(
        f"{'PASS' if passed else 'FAIL'}: any acceptable page in the top {TOP} for "
        f"{any_top} of {total} (needs {PASS_AT_LEAST})"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    name = args[0] if args else "cos330"
    run = retrieval.main if "--retrieval" in sys.argv[1:] else main
    sys.exit(asyncio.run(run(name)))
