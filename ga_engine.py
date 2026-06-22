"""
Genetic Algorithm engine for Precedence-Constrained TSP (pickup & delivery).

Chromosome: a permutation of all pickup + delivery point IDs.
Basecamp is always the first and last stop (not part of the chromosome).
Constraint: each pickup must appear before all of its delivery targets.
"""

import random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dist(dist_matrix: list, idx: dict, pid1: str, pid2: str) -> float:
    """Road distance (meters) between two point IDs via pre-computed matrix."""
    return dist_matrix[idx[pid1]][idx[pid2]]


# ---------------------------------------------------------------------------
# Repair — ensure every pickup appears before its deliveries
# ---------------------------------------------------------------------------

def repair(chrom: list, pickup_set: set, precedence: dict) -> list:
    """
    Move any pickup that appears AFTER one of its deliveries
    to just before that delivery. Repeat until no violations remain.

    Args:
        chrom: chromosome (list of point IDs)
        pickup_set: set of IDs that are pickups
        precedence: dict {pickup_id: [delivery_id, ...]}

    Returns:
        Repaired chromosome (new list).
    """
    c = chrom[:]
    changed = True
    iterations = 0

    while changed and iterations < len(c) * 2:
        changed = False
        iterations += 1

        for a, targets in precedence.items():
            if a not in c:
                continue
            a_pos = c.index(a)

            for t in targets:
                if t not in c:
                    continue
                t_pos = c.index(t)

                if a_pos > t_pos:
                    c.pop(a_pos)
                    new_pos = c.index(t)
                    c.insert(new_pos, a)
                    changed = True
                    break
            if changed:
                break

    return c


# ---------------------------------------------------------------------------
# Route total distance
# ---------------------------------------------------------------------------

def route_total(bc: str, chrom: list, dist_matrix: list, idx: dict) -> float:
    """
    Total route distance: BC -> chrom[0] -> ... -> chrom[-1] -> BC.
    Uses pre-computed distance matrix for O(1) lookups.
    """
    if not chrom:
        return 0.0

    total = _dist(dist_matrix, idx, bc, chrom[0])
    for k in range(len(chrom) - 1):
        total += _dist(dist_matrix, idx, chrom[k], chrom[k + 1])
    total += _dist(dist_matrix, idx, chrom[-1], bc)
    return total


# ---------------------------------------------------------------------------
# Fitness
# ---------------------------------------------------------------------------

def fitness(chrom: list, bc: str, pickup_set: set,
            precedence: dict, dist_matrix: list, idx: dict) -> float:
    """Repair chromosome then compute total route distance (lower = better)."""
    c = repair(chrom, pickup_set, precedence)
    return route_total(bc, c, dist_matrix, idx)


# ---------------------------------------------------------------------------
# Random valid individual
# ---------------------------------------------------------------------------

def random_valid_individual(pickups: list, delivery_map: dict,
                            precedence: dict, pickup_set: set) -> list:
    """
    Build a random chromosome that already satisfies precedence:
    1. Shuffle pickup order.
    2. Collect and shuffle all delivery IDs.
    3. Insert each delivery at a random position AFTER its owner pickup.
    4. Final repair pass for safety.
    """
    amenity_order = pickups[:]
    random.shuffle(amenity_order)

    all_targets = []
    for a in pickups:
        all_targets.extend(delivery_map.get(a, []))
    random.shuffle(all_targets)

    # Start with pickups in shuffled order
    result = list(amenity_order)

    # Insert each delivery after its owner
    for t in all_targets:
        # Find owner pickup for this delivery
        owner = None
        for a, targets in precedence.items():
            if t in targets:
                owner = a
                break
        if owner is None:
            result.append(t)
            continue

        owner_pos = result.index(owner)
        insert_pos = random.randint(owner_pos + 1, len(result))
        result.insert(insert_pos, t)

    return repair(result, pickup_set, precedence)


# ---------------------------------------------------------------------------
# Order Crossover (OX)
# ---------------------------------------------------------------------------

def ox_crossover(p1: list, p2: list, pickup_set: set,
                 precedence: dict) -> list:
    """
    Order Crossover: copy a random segment from p1, fill remaining
    positions with genes from p2 in their original order.
    """
    n = len(p1)
    a, b = sorted(random.sample(range(n), 2))

    child = [None] * n
    child[a:b + 1] = p1[a:b + 1]

    fill = [g for g in p2 if g not in child]
    ptr = 0
    for i in range(n):
        if child[i] is None:
            child[i] = fill[ptr]
            ptr += 1

    return repair(child, pickup_set, precedence)


# ---------------------------------------------------------------------------
# Swap Mutation
# ---------------------------------------------------------------------------

def mutate(chrom: list, rate: float, pickup_set: set,
           precedence: dict) -> list:
    """Swap mutation: each gene has `rate` chance to swap with another random gene."""
    c = chrom[:]
    for i in range(len(c)):
        if random.random() < rate:
            j = random.randint(0, len(c) - 1)
            c[i], c[j] = c[j], c[i]
    return repair(c, pickup_set, precedence)


# ---------------------------------------------------------------------------
# Main GA loop
# ---------------------------------------------------------------------------

def run_pctsp_ga(
    bc: str,
    pickups: list,
    delivery_map: dict,
    dist_matrix: list,
    ordered_points: list,
    pop_size: int = 80,
    generations: int = 200,
    mutation_rate: float = 0.03,
    elite_size: int = 8,
) -> tuple:
    """
    Run the Precedence-Constrained TSP Genetic Algorithm.

    Args:
        bc: basecamp point ID
        pickups: list of pickup point IDs
        delivery_map: {pickup_id: [delivery_id, ...]}
        dist_matrix: N×N distance matrix (meters) from OSRM or Haversine
        ordered_points: list of point IDs matching matrix row/col order
        pop_size: population size per generation
        generations: number of generations to evolve
        mutation_rate: probability of swap per gene (0.03 = 3%)
        elite_size: number of top individuals carried over unchanged

    Returns:
        (best_chromosome, best_distance, history_list)
    """
    # Index map: point_id -> matrix row/col index
    idx = {pid: i for i, pid in enumerate(ordered_points)}
    # Build precedence dict: {pickup_id: [delivery_ids]}
    precedence = {a: list(delivery_map.get(a, [])) for a in pickups}
    pickup_set = set(pickups)

    # --- Step 1: Initialize population ---
    population = []
    for _ in range(pop_size):
        ind = random_valid_individual(pickups, delivery_map,
                                      precedence, pickup_set)
        population.append(ind)

    best_chrom = population[0][:]
    best_dist = fitness(best_chrom, bc, pickup_set, precedence, dist_matrix, idx)
    history = []

    # --- Main GA loop ---
    for gen in range(generations):
        # Step 2: Evaluate & sort (ascending = best first)
        scored = sorted(
            population,
            key=lambda c: fitness(c, bc, pickup_set, precedence, dist_matrix, idx)
        )
        gen_best_dist = route_total(
            bc, repair(scored[0], pickup_set, precedence), dist_matrix, idx
        )

        # Step 3: Track best overall
        if gen_best_dist < best_dist:
            best_dist = gen_best_dist
            best_chrom = repair(scored[0], pickup_set, precedence)[:]

        history.append(round(best_dist, 1))

        # Step 4: Elitism — carry top individuals forward
        new_pop = [repair(c, pickup_set, precedence)
                   for c in scored[:elite_size]]

        # Steps 5-7: Reproduce until population is full
        while len(new_pop) < pop_size:
            # Selection: pick from top 25%
            top_k = max(2, pop_size // 4)
            p1 = random.choice(scored[:top_k])
            p2 = random.choice(scored[:top_k])

            # Crossover
            child = ox_crossover(p1, p2, pickup_set, precedence)

            # Mutation
            child = mutate(child, mutation_rate, pickup_set, precedence)

            new_pop.append(child)

        # Step 8: Replace population
        population = new_pop

    return best_chrom, best_dist, history
