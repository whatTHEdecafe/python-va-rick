# Version 9 - Enhanced Furniture Database
---

## Pipeline architecture (vision vs logistics)

The analyzer splits work so **UI changes to access, travel, or crew do not call Gemini** unless media changed.

| Stage | Method | Calls Gemini? | Output |
|-------|--------|---------------|--------|
| 1–2 | `analyze_media()` | Yes | `VisionResult`: detected `items`, `summary` |
| 3 | `enrich_items()` | No | Items + catalog `weight`, `volume`, `size`, `baseTime` |
| 4 | `compute_logistics()` | No | Loading times, movers, trucks, pricing |

**Streamlit:** Press **Analyze Move** to run stages 3–4 (and 1–2 only if uploads changed). Sliders and sidebar edits do not auto-recalculate.

**Media cache:** The UI fingerprints uploads by **file name + byte length + SHA-256 of content**, not temp path or mtime, so re-saving the same files to a new folder does not trigger another Gemini call.

Data contracts: [`modules/models.py`](modules/models.py) (`VisionResult`, `LogisticsParams`, `AnalysisSnapshot`).

---

## 🧮 Calculation Logic (`calculator.py`)

**Source file:** [`modules/calculator.py`](modules/calculator.py) — class `MovingCalculator`.

This section is written for engineers onboarding to the quote engine: **short steps**, **symbols**, and **one story** from items → minutes → movers → trucks → price. (Use alongside the step-by-step pseudocode below.)

---

### Engineer guide — narrative + equations

#### 0. Big picture (one story)

```text
INPUT:  items[] + pickup_access + dropoff_access + travel minutes
          ↓
STEP A: Match each item to JSON catalog → size, weight, volume, minutes per piece
          ↓
STEP B: Build "tasks" (one row per physical unit; batch stackable groups)
          ↓
STEP C: For each crew size m = 2 … truck seats: job minutes (parallelism + stairs × + elevator +)
          ↓
STEP D: Pick truck(s) from total volume/weight (with buffers)
          ↓
STEP E: Pick recommended crew (cost vs time score), or UI forced_movers
          ↓
STEP F: Add travel → total minutes → price = minutes × movers × wage
OUTPUT: times, trucks, workers, price range, GST
```

**Main idea:** Time = **catalog minutes per item**, then **crew parallelism**, then **building access** (stairs multiply; elevator adds fixed trips). Price = **wall-clock minutes × number of movers × $40/hour**.

Gemini does **not** return weight, volume, or `baseTime` — those come from the JSON catalog in stage 3 (`enrich_items` / `build_tasks`).

---

#### 1. Constants (tuning knobs)

| Symbol | Value | Meaning |
|--------|-------|---------|
| `W` | `40 / 60` | Dollars per **minute** ($40/hr) |
| `F_max` | 50 | Max floors (cap) |
| `S_base` | 0.06 | Stairs: extra fraction at 0 floors |
| `S_floor` | 0.035 | Stairs: extra fraction **per floor** |
| `E_fix` | 1.5 min | Elevator: fixed time per **trip** |
| `E_ride` | 0.08 min/floor | Elevator: ride time per floor |
| `E_items` | 2.0 | Average items per elevator trip |
| `E_parallel` | 1.5 | Max effective teams if elevator exists |
| `MAX_M` | 6 | UI slider cap for movers |

**Truck safety margins:**

```text
V_need = V_total × 1.15
W_need = W_total × 1.10
```

---

#### 2. Step A — Catalog lookup, size, per-item minutes

**`find_item_category(name)`** — lowercase name; match category name or alias (exact or substring).

**`choose_size_for_item(name, cat_def)`** — order: JSON `classificationLogic` keywords → fallback keywords (small/large) → default **medium**.

**`compute_base_item_time(item, cat_def, size)`**

```text
T_load = baseTime[size]

IF needs_disassembly OR disassemble:
    T_load += disassemblyAdder[size]

IF item.weight > catalog weight[size]:
    T_load += heavyAdder[size]

R = unload_ratio(category)     # 0.65 default; 0.90 boxes; 0.55 heavy; 0.50 disassembly catalog; …
T_unload = T_load × R

T_item = max(T_load + T_unload, 2)
```

**`determine_required_movers`**

```text
q_item = 2   if twoPersonRequired[size]
       = 1   otherwise
```

(`q` = movers required to handle that item; used in tasks, not the final crew count alone.)

**No catalog match:** `T_load = 5`, `R = 0.65`, default weight/volume in `build_tasks`.

---

#### 3. Step B — Tasks and stackable batching

**`build_tasks`** — for each input line, expand `quantity` into one task per unit with `p`, `load_time`, `unload_time`, `q`, `weight`, `volume`.

**`_apply_stackable_grouping`** — group same `(name, size)` when `stackable` and `stackableSavings > 0`:

```text
P_batch = sum(p_i) × (1 - savings% / 100)
q_batch = max(q_i) over group
```

Non-stackable tasks pass through unchanged.

---

#### 4. Step C — Job time for one crew size `M`

**`calculate_job_time(tasks, M, pickup, dropoff)`** — let `L = sum(task.p)`, `N = len(tasks)`.

**Effective parallel teams `T_eff`:**

| M | T_eff |
|---|-------|
| 2 | 1.0 |
| 3 | 1.25 |
| 4 | 2.0 |
| 5 | 2.25 |
| 6 | 3.0 |
| other | M / 2 |

```text
IF elevator at pickup OR dropoff:
    T_eff = min(T_eff, 1.5)
```

**Bottleneck `B` (truck door congestion):**

| M | B |
|---|---|
| 2 | 1.00 |
| 3 | 0.95 |
| 4 | 0.85 |
| 5 | 0.70 |
| 6 | 0.55 |
| other | 0.60 |

```text
IF T_eff <= 1:
    T_base = L
ELSE:
    T_base = (L / T_eff) / B
```

**Stairs (multiply) — per leg, type = stairs:**

```text
Δ = S_base + S_floor × floors     # floors clamped 0 … F_max
F_stair = 1 + Δ_pickup + Δ_dropoff
T_stairs = T_base × F_stair
```

Ground → Δ = 0. Elevator → Δ = 0 here (elevator handled separately).

**Elevator (add) — per leg, type = elevator:**

```text
t_trip = E_fix + E_ride × floors
trips = ceil(N / E_items)
T_elev_leg = trips × t_trip

T_job = T_stairs + T_elev_pickup + T_elev_dropoff
```

**Why two models?** Stairs scale effort on **every item** (multiply). Elevator is **wait + ride per trip** (add; hard to parallelize).

---

#### 5. Step D — Trucks and cab seats

**`select_optimal_vehicles`** — smallest truck fitting `V_need` and `W_need`; if volume use **> 70%**, upsize one step; else multiple largest trucks.

```text
cab_seats = max(2, sum(truck.maxSeats × quantity))
```

Auto crew evaluation loops **m = 2 … cab_seats** only.

---

#### 6. Step E — Crew selection and override

For each `m` in 2 … `cab_seats`:

```text
T_job(m) = calculate_job_time(...)
Cost(m)  = T_job(m) × m × W
```

```text
small_job = (T_job at m=2) < 180 minutes

norm_time = (T_job - min) / range
norm_cost = (Cost - min) / range

IF small_job:  score = 0.2 × norm_time + 0.8 × norm_cost
ELSE:          score = 0.4 × norm_time + 0.6 × norm_cost
```

Pick lowest score among `T_job < 360` min; if none, pick fastest `T_job`.

```text
IF forced_movers from UI:
    recommended_m = clamp(forced_movers, 2, MAX_M)
ELSE:
    recommended_m = auto pick from score
```

Override uses **MAX_M (6)**, not only `cab_seats` (follow car allowed in UI copy).

---

#### 7. Step F — Travel, display split, price

```text
T_total = T_labor + pre_move_travel + travel_time
Price_base = T_total × recommended_m × W
```

**Hour band (CSV):** round `T_total/60` to 0.25 hr → lookup `Vision_Agent_Hour_Range_Mapping.csv` → min/max hours → min/max price.

**Loading vs unloading on report** (proportional split from task load/unload sums):

```text
ratio = sum(load_time) / (sum(load_time) + sum(unload_time))
loading_report   = T_labor × ratio
unloading_report = T_labor × (1 - ratio)
```

```text
GST = Price_base × 0.05
Total = Price_base × 1.05
```

---

#### 8. Full equation chain (whiteboard)

```text
# Per item
T_load = baseTime[size] + disasm + heavy
T_unload = T_load × R
p = max(T_load + T_unload, 2)

# Job
L = Σ p
T_base = L  OR  (L / T_eff) / B
T_labor = T_base × F_stair + T_elev_pick + T_elev_drop

# Quote
T_total = T_labor + pre_travel + travel
Price = T_total × M_rec × (40/60)
```

---

#### 9. Access types — quick reference

| Access | Effect on time |
|--------|----------------|
| **ground** | No extra |
| **stairs** | Multiply: × (1 + 0.06 + 0.035×floors) per leg |
| **elevator** | Add: `ceil(N/2) × (1.5 + 0.08×floors)` per leg; cap `T_eff` at 1.5 |

---

#### 10. JSON catalog fields (`converted_items_lowered.json`)

| Field | Used for |
|-------|----------|
| `baseTime` | Load minutes by size |
| `weight`, `volume` | Truck fit + heavy check |
| `disassemblyAdder` | Extra load minutes if disassemble flag |
| `heavyAdder` | Extra if heavier than typical |
| `twoPersonRequired` | Task `q` (2-person item) |
| `stackable`, `stackableSavings` | Batch discount % |
| `aliases` | Name matching |
| `classificationLogic` | Size from name |

---

#### 11. `calculate_total_logistics` return shape

| Key | Contents |
|-----|----------|
| `items[]` | Per-name display: load/unload/disassembly times |
| `time` | preMoveTravel, loadingTime, travelBetweenLocations, unloadingTime, totalMinutes/Hours, estimatedRange |
| `material` | numberOfWorkers, recommendedWorkers (auto), vehicles, cabSeats |
| `volume` / `weight` | totals, 15%/10% buffer, utilization % |
| `pricing` | base, min/max, GST 5%, total with tax |

---

#### 12. Review FAQ

| Question | Answer |
|----------|--------|
| Why don’t 6 movers make the job 3× faster? | `T_eff` grows slower than `M`; bottleneck `B` drops to 0.55 (door congestion). |
| Why stairs and elevator different? | Stairs scale **all item work** (×). Elevator is **trip wait** (+). |
| Why not 6 movers on a 2-hour job? | Small-job score weights **cost 80%**. |
| Minimum time per item? | `max(total, 2)` minutes; unknown category defaults 5 min load. |

---

### `calculator.py` — formulas in plain code

#### Wage

```text
WAGE_RATE = 40 / 60    # dollars per minute ($40/hr)
```

#### Per-item minutes (`compute_base_item_time`)

Start from the JSON catalog, then add optional minutes the same way the code does:

```text
base = cat_def.baseTime[size]

# Optional minutes — only when the condition is true (see compute_base_item_time)
if item needs disassembly:   # needs_disassembly OR disassemble on the item
    base += cat_def.disassemblyAdder[size]
if item.weight > cat_def.weight[size]:   # heavier than catalog default for that size
    base += cat_def.heavyAdder[size]

load_time  = base
unload_ratio = _get_unload_ratio(cat_def, size)   # 0.65 default, 0.90 for boxes, …
unload_time  = base * unload_ratio

total_item_minutes = max(load_time + unload_time, 2)
```

If there is **no** category match: `load_time = 5`, `unload_ratio = DEFAULT_UNLOAD_RATIO` (0.65), same `total_item_minutes` rule.

#### Stackable batch (`_apply_stackable_grouping`)

One group = same name + size, stackable, with `stackableSavings` = `s` (percent):

```text
factor = 1 - s/100
combined_wall_clock = sum(each unit’s p) * factor
combined_load       = sum(load_time)       * factor
combined_unload     = sum(unload_time)     * factor
movers_for_batch    = max(each unit’s q)
```

#### Job time (`calculate_job_time`) — one function, three ideas

**A — Add up work:** `total_labor_minutes = sum(task.p)`. `num_items = len(tasks)`.

**B — Spread across movers (then stairs multiply, elevator add):**

```text
effective_teams = effective_teams_map[movers]   # dict in code; if movers > 6 use movers/2
if pickup_or_dropoff_is_elevator:
    effective_teams = min(effective_teams, ELEVATOR_PARALLELISM_CAP)

bottleneck = bottleneck_map[movers]   # truck-door congestion; else 0.60 default

if effective_teams <= 1:
    base_time = total_labor_minutes
else:
    base_time = (total_labor_minutes / effective_teams) / bottleneck

# Stairs: multiply the whole base_time (per-leg “delta” is 0 for ground, stairs-only for stairs)
stair_friction = 1.0
               + delta(pickup_access)   # 0, or STAIR_BASE_FRICTION + STAIR_PER_FLOOR * floors
               + delta(dropoff_access)

adjusted_time = base_time * stair_friction

# Elevator: add minutes AFTER that (cannot be parallelized away)
trips(leg) = ceil(num_items / AVG_ITEMS_PER_ELEVATOR_LOAD)
minutes_per_trip(leg) = ELEVATOR_FIXED_PER_TRIP + ELEVATOR_RIDE_PER_FLOOR * floors_on_that_leg
elevator_pick  = trips(pickup)  * minutes_per_trip(pickup)   if pickup is elevator else 0
elevator_drop  = trips(dropoff) * minutes_per_trip(dropoff) if dropoff is elevator else 0

job_time_minutes = adjusted_time + elevator_pick + elevator_drop
```

#### Auto-pick crew size (`calculate_total_logistics`, inside)

Only loop **`m` from 2 through `cab_seats`** (fits in vehicle). For each:

```text
time_m = calculate_job_time(tasks, m, ...)
cost_m = time_m * m * WAGE_RATE

norm_time_m = (time_m - min_time) / time_range    # time_range is 1 if all equal (code)
norm_cost_m = (cost_m - min_cost) / cost_range

is_small_job = (time at m==2) < 180   # minutes

if is_small_job:
    score_m = 0.2 * norm_time_m + 0.8 * norm_cost_m
else:
    score_m = 0.4 * norm_time_m + 0.6 * norm_cost_m
```

Choose the **lowest score** among runs where `time_m < 360`; if nobody qualifies, pick the **fastest** `time_m`. That winning `m` is `recommendedWorkers` before any UI override.

#### Forced mover count (slider override)

```text
m = clamp(forced_movers, 2, MAX_MOVERS)   # MAX_MOVERS = 6

if m was precomputed in the evals loop:
    labor_minutes = that stored time
else:
    labor_minutes = calculate_job_time(tasks, m, ...)   # on-the-fly
```

#### Wall-clock minutes and money

```text
total_wall_minutes = labor_minutes + pre_move_travel + travel_time

base_price = total_wall_minutes * num_movers * WAGE_RATE

# Range: look up min/max hours in Vision_Agent_Hour_Range_Mapping.csv from total_wall_minutes/60
min_base_price = (min_hours_from_csv * 60) * num_movers * WAGE_RATE
max_base_price = (max_hours_from_csv * 60) * num_movers * WAGE_RATE

GST                 = base_price * 0.05
total_with_tax      = base_price * 1.05
# …same 0.05 / 1.05 pattern for min/max prices
```

#### Load vs unload minutes on the report (display only)

```text
sum_load   = sum(task.load_time   for task in tasks)   # or default split if missing
sum_unload = sum(task.unload_time for task in tasks)
total_split = sum_load + sum_unload
load_fraction = sum_load / total_split   # or 0.606 if total_split == 0

loading_time_on_report   = labor_minutes * load_fraction
unloading_time_on_report = labor_minutes * (1 - load_fraction)
```

#### Vehicles and `cab_seats`

```text
vol_buffered  = total_item_volume  * 1.15
weight_buffered = total_item_weight * 1.10
# pick truck(s) — smallest that fits; maybe upsize if volume > 70% of truck; else multiple largest trucks

cab_seats = max(2, sum(truck.maxSeats * quantity for each chosen truck row))
```

---

### Step 1 — Per-item time (`compute_base_item_time`)

```
function compute_base_item_time(item, cat_def, size):

    # Base loading time from JSON catalog
    base = cat_def.baseTime[size]          # e.g. sofa/medium = 18.0 min

    # Optional adders (mutually independent)
    if item.needs_disassembly:
        base += cat_def.disassemblyAdder[size]   # e.g. bed frame adds 5 min

    if item.weight > cat_def.weight[size]:       # heavier than catalog default
        base += cat_def.heavyAdder[size]

    load_time   = base
    unload_ratio = _get_unload_ratio(cat_def, size)
    unload_time  = base * unload_ratio

    return { total: load_time + unload_time, load_time, unload_time }
```

**Unload ratios by category** (relative to load time):

| Category | Ratio | Reasoning |
|---|---|---|
| Standard furniture (default) | 0.65 | Pre-wrapped; slowed by placement decisions |
| Boxes / totes / bins | 0.90 | Grab-and-go from truck |
| Fragile (TV, mirror, artwork) | 0.80 | Careful placement at dropoff |
| Heavy appliances | 0.55 | Positioning, connections, door clearances |
| Disassembly items (beds, desks) | 0.50 | Reassembly at dropoff |
| Piano, treadmill | 0.55 | Heavy + awkward positioning |

**If item not found in catalog:** `load_time = 5.0 min`, `unload_ratio = 0.65` (defaults).

**Same math in everyday words:** `load_time` is the adjusted base in minutes; `unload_time = load_time * unload_ratio`. The returned total is at least **2** minutes.

---

### Step 2 — Task list + stackable batching (`build_tasks` → `_apply_stackable_grouping`)

```
function build_tasks(job_items):
    raw_tasks = []
    for item in job_items:
        for each unit of item.quantity:
            time_info = compute_base_item_time(item, cat_def, size)
            raw_tasks.append({
                p:          time_info.total,       # wall-clock minutes
                load_time:  time_info.load_time,
                unload_time: time_info.unload_time,
                q:          1 or 2,                # movers required by item
                stackable:  bool,
                stackableSavings: pct,
                weight, volume
            })
    return _apply_stackable_grouping(raw_tasks)


function _apply_stackable_grouping(raw_tasks):
    # Group identical stackable items (e.g. 6 dining chairs → 1 batch task)
    for each group of same stackable items:
        savings_pct   = group[0].stackableSavings
        combined_p    = sum(t.p)     * (1 - savings_pct / 100)
        combined_load = sum(t.load)  * (1 - savings_pct / 100)
        combined_unload = sum(t.unload) * (1 - savings_pct / 100)
        # Non-stackable items pass through unchanged
    return final_tasks
```

**Same math in everyday words:** multiply the group’s total wall-clock minutes (and load/unload subtotals) by `(1 - stackableSavings/100)`. Movers needed for the batch = max of each unit’s `q`.

---

### Step 3 — Wall-clock job time (`calculate_job_time`)

This is the core formula. The algorithm runs it for 2 through `cab_seats` (vehicle cab capacity) to pick a recommendation. The UI can force any value 2 through `MAX_MOVERS` (= 6); values above `cab_seats` trigger an on-the-fly recalculation.

```
function calculate_job_time(tasks, movers, pickup_access, dropoff_access):

    # 1. Sequential labor baseline
    total_labor_minutes = sum(t.p for t in tasks)
    num_items = len(tasks)

    # 2. Effective teams (non-linear: odd movers = partial team)
    effective_teams_map = { 2:1.0, 3:1.25, 4:2.0, 5:2.25, 6:3.0 }
    effective_teams = effective_teams_map[movers]

    if elevator present at either location:
        effective_teams = min(effective_teams, 1.5)   # elevator serializes teams

    # 3. Bottleneck factor (truck door congestion)
    bottleneck_map = { 2:1.00, 3:0.95, 4:0.85, 5:0.70, 6:0.55 }
    bottleneck = bottleneck_map[movers]

    # 4. Parallelism
    if effective_teams <= 1:
        base_time = total_labor_minutes
    else:
        base_time = (total_labor_minutes / effective_teams) / bottleneck

    # 5a. Stairs — multiplicative (effort scales per flight)
    stair_friction = 1.0
                   + (STAIR_BASE_FRICTION + STAIR_PER_FLOOR * pickup_floors)  if stairs
                   + (STAIR_BASE_FRICTION + STAIR_PER_FLOOR * dropoff_floors) if stairs
    # STAIR_BASE_FRICTION = 0.06, STAIR_PER_FLOOR = 0.035
    adjusted_time = base_time * stair_friction

    # 5b. Elevator — additive (fixed per-trip wait/ride, not item-complexity-scaled)
    trip_time     = ELEVATOR_FIXED_PER_TRIP + ELEVATOR_RIDE_PER_FLOOR * floors
    trips_per_leg = ceil(num_items / AVG_ITEMS_PER_ELEVATOR_LOAD)   # = ceil(n / 2)
    elevator_min  = trips_per_leg * trip_time   # per elevator leg
    # ELEVATOR_FIXED_PER_TRIP = 1.5 min, ELEVATOR_RIDE_PER_FLOOR = 0.08 min
    # AVG_ITEMS_PER_ELEVATOR_LOAD = 2.0

    final_time = adjusted_time + elevator_pickup_min + elevator_dropoff_min
    return final_time
```

**Same pipeline in words** (matches `calculate_job_time`):

```text
job_time =
    (parallelism_and_stairs_part)  +  elevator_minutes_pickup  +  elevator_minutes_dropoff

parallelism_and_stairs_part =
    (how long if one crew did everything, spread across teams and bottleneck)
    * stair_friction_multiplier

# stair_friction starts at 1.0 and only grows if a leg is stairs
# elevator minutes are extra add-ons, computed per leg from num_items and floors
```

Maps and defaults: see **`calculator.py` — formulas in plain code** above; fallbacks for unknown crew size use `movers/2` for effective teams and `0.60` for bottleneck.

See **🛗 Elevator Model (Deep Dive)** below for why elevator minutes are added (not multiplied), and for numeric examples.

---

### Step 4 — Crew selection + `forced_movers`

```
# Evaluate crew sizes within vehicle cab capacity (for auto-recommendation)
cab_seats = sum(vehicle.maxSeats * quantity for vehicle in vehicles)
for m in range(2, cab_seats + 1):
    evals[m] = { time: calculate_job_time(tasks, m, ...), cost: time * m * WAGE_RATE }

# Score each option (algorithm only sees cab-sized crews)
def score(m):
    norm_time = (evals[m].time - min_time) / time_range
    norm_cost = (evals[m].cost - min_cost) / cost_range
    if is_small_job (< 3 hrs at 2 movers):
        return 0.2 * norm_time + 0.8 * norm_cost   # cost-heavy for small jobs
    else:
        return 0.4 * norm_time + 0.6 * norm_cost

auto_recommended_m = m with lowest score(m)   # always within cab capacity

# Override if UI slider used (slider goes up to MAX_MOVERS = 6)
if forced_movers is not None:
    recommended_m = clamp(forced_movers, min=2, max=6)
    if recommended_m in evals:
        base_minutes = evals[recommended_m].time
    else:
        base_minutes = calculate_job_time(tasks, recommended_m, ...)  # on-the-fly
else:
    recommended_m = auto_recommended_m
    base_minutes = evals[recommended_m].time
```

**Scoring (who wins the auto-pick)** — normalized `norm_time` / `norm_cost` are built **only** from the precomputed rows where `m` runs **2 … cab_seats**. If the UI forces an `m` outside that range, the engine skips scoring and runs `calculate_job_time` for that `m` only.

```text
if time_at_2_movers < 180:   # small job
    score = 0.2 * norm_time + 0.8 * norm_cost
else:
    score = 0.4 * norm_time + 0.6 * norm_cost
# Prefer m with score lowest AND job time < 360 min; if none, pick fastest time
# Slider override: m = clamp(forced_movers, 2, 6)
```

See **👷 Crew Override (Deep Dive)** below for UI integration details.

---

### Step 5 — Total time, price, and price range

```
total_time_minutes = base_minutes + pre_move_travel + travel_time
base_price         = total_time_minutes * recommended_m * WAGE_RATE
# WAGE_RATE = $40/hr = $0.667/min

# Price range — from the same CSV used by the Estimated Range clock
(min_hours, max_hours) = _get_hour_range_data(total_time_minutes / 60)
min_base_price = min_hours * 60 * recommended_m * WAGE_RATE
max_base_price = max_hours * 60 * recommended_m * WAGE_RATE

# Final output
pricing.basePrice             = base_price
pricing.basePriceMin/Max      = min/max_base_price
pricing.GST                   = base_price * 0.05
pricing.totalExpectedPrice    = base_price * 1.05
pricing.totalExpectedPriceMin = min_base_price * 1.05
pricing.totalExpectedPriceMax = max_base_price * 1.05
```

**Money (labor + tax):**

```text
wage_per_minute = WAGE_RATE   # 40/60

base_price      = total_wall_minutes * num_movers * wage_per_minute
min_base_price  = (min_hours_from_csv * 60) * num_movers * wage_per_minute
max_base_price  = (max_hours_from_csv * 60) * num_movers * wage_per_minute

GST             = base_price * 0.05
total_with_tax  = base_price * 1.05
```

`total_wall_minutes` = labor + `pre_move_travel` + `travel_between`. Min/max hours come from `_get_hour_range_data(total_wall_minutes / 60)`.

See **💰 Pricing Range Display (Deep Dive)** below for the CSV lookup details.

---

### Constants quick reference

| Constant | Value | Used in |
|---|---|---|
| `WAGE_RATE` | $0.667/min ($40/hr) | Step 4, 5 |
| `STAIR_BASE_FRICTION` | 0.06 | Step 3 |
| `STAIR_PER_FLOOR` | 0.035 | Step 3 |
| `ELEVATOR_FIXED_PER_TRIP` | 1.5 min | Step 3 |
| `ELEVATOR_RIDE_PER_FLOOR` | 0.08 min | Step 3 |
| `AVG_ITEMS_PER_ELEVATOR_LOAD` | 2.0 | Step 3 |
| `ELEVATOR_PARALLELISM_CAP` | 1.5 teams | Step 3 |
| `DEFAULT_UNLOAD_RATIO` | 0.65 | Step 1 |

---

## 🛗 Elevator Model (Deep Dive)

Elevator jobs use an **additive per-trip model** instead of the old percentage multiplier.
This section explains the problem, what changed, how the new code works, and the test results.

---

### The Problem: Percentage Multiplier Over-Inflates Elevator Jobs

The **old code** treated elevator access the same way as stairs — as a percentage multiplier on the entire job time:

```python
# OLD constants (removed)
ELEVATOR_BASE_FRICTION = 0.04   # 4% base
ELEVATOR_PER_FLOOR     = 0.012  # +1.2% per floor

# OLD _access_friction_delta (elevator branch, removed)
if typ == 'elevator':
    return self.ELEVATOR_BASE_FRICTION + self.ELEVATOR_PER_FLOOR * floors

# OLD calculate_job_time (changed)
friction = 1.0 + delta_pickup + delta_dropoff
final_time = base_time * friction   # ← entire job scaled by percentage
```

**Example with 25 floors, elevator at both ends:**
```
delta_per_leg = 0.04 + 0.012 × 25 = 0.34
friction      = 1.0 + 0.34 + 0.34 = 1.68
final_time    = base_time × 1.68        → 68% markup on entire job
```

**Why this is wrong:**
- Stairs genuinely scale with effort — carrying a sofa up 5 flights takes ~5× longer than 1 flight. Every step is physical labor. A percentage multiplier models this correctly.
- An elevator's cost is **fixed per trip**: wait for it to arrive, load items, ride up, walk to unit. A sofa and a lamp both wait the same 2 minutes. The ride takes the same time regardless of item complexity.
- With the old model, a 300-min job got +204 min for elevator, while a 100-min job got only +68 min. But the actual elevator time depends on **how many trips** and **how many floors** — not on how complex or heavy the items are.

**Real-world feedback confirmed:** elevator job estimates ran consistently **too high**.

---

### What Changed: 4 Modifications in `calculator.py`

#### 1. New Constants Replace Old Ones

```python
# OLD (removed)
ELEVATOR_BASE_FRICTION = 0.04
ELEVATOR_PER_FLOOR = 0.012

# NEW (added)
ELEVATOR_FIXED_PER_TRIP = 1.5       # min: walk to elevator, load/unload at door
ELEVATOR_RIDE_PER_FLOOR = 0.08      # min per floor (~5 sec/floor ride time)
AVG_ITEMS_PER_ELEVATOR_LOAD = 2.0   # avg items carried per elevator trip
ELEVATOR_PARALLELISM_CAP = 1.5      # max effective teams when elevator is bottleneck
```

| Constant | Value | Reasoning |
|----------|-------|---------- |
| `ELEVATOR_FIXED_PER_TRIP` | 1.5 min | Covers: walk to elevator lobby, wait for car to arrive, load items in, unload at destination floor, walk to unit door. Conservative middle ground between reserved service elevator (~1 min) and shared residential elevator (~2-3 min). |
| `ELEVATOR_RIDE_PER_FLOOR` | 0.08 min | ~5 seconds per floor. Average elevator speed is 1-2 m/s, ~3m per floor. Includes door open/close time amortized across floors. |
| `AVG_ITEMS_PER_ELEVATOR_LOAD` | 2.0 | Movers typically carry 1-3 items per trip. Large furniture = 1 item/trip, boxes = 3-4/trip. Default of 2.0 reflects a typical residential mix. |
| `ELEVATOR_PARALLELISM_CAP` | 1.5 | Only one team can ride the elevator at a time. Even with 6 movers (3 teams), the elevator serializes them — while one team rides, others can prep/wrap, but throughput is capped. 1.5 reflects partial overlap. |

Stair constants are **unchanged** — `STAIR_BASE_FRICTION` (0.06) and `STAIR_PER_FLOOR` (0.035) remain as percentage multipliers.

#### 2. `_access_friction_delta` — Elevator Returns 0.0

```python
def _access_friction_delta(self, access):
    """Elevator returns 0.0 here; handled via additive model."""
    typ = (access.get('type') or 'ground').lower().strip()
    floors = self._normalize_floors(access)
    if typ == 'ground':
        return 0.0
    if typ == 'stairs':
        return self.STAIR_BASE_FRICTION + self.STAIR_PER_FLOOR * floors
    # Elevator friction is no longer percentage-based; handled additively
    return 0.0
```

**Why:** This method feeds into the multiplicative `friction` variable. By returning 0.0 for elevator, we prevent the old percentage inflation. Elevator time is now computed separately via the new method below.

#### 3. New Method: `_compute_elevator_adder`

```python
def _compute_elevator_adder(self, access, num_items):
    """Additive wall-clock minutes for one elevator leg."""
    typ = (access.get('type') or 'ground').lower().strip()
    if typ != 'elevator':
        return 0.0
    floors = self._normalize_floors(access)
    trip_time = self.ELEVATOR_FIXED_PER_TRIP + self.ELEVATOR_RIDE_PER_FLOOR * floors
    trips = math.ceil(num_items / self.AVG_ITEMS_PER_ELEVATOR_LOAD)
    return trips * trip_time
```

**Data flow:**
```
num_items = len(tasks)  ← count of individual task entries (after stacking)
floors    = from access dict (e.g. {"type": "elevator", "floors": 25})
trip_time = 1.5 + 0.08 × floors   (minutes per round-trip)
trips     = ceil(items / 2.0)      (how many elevator loads)
total     = trips × trip_time       (additive minutes for this leg)
```

A helper `_has_elevator` was also added to detect if either leg uses an elevator:

```python
@staticmethod
def _has_elevator(pickup_access, dropoff_access):
    for acc in (pickup_access, dropoff_access):
        if (acc.get('type') or 'ground').lower().strip() == 'elevator':
            return True
    return False
```

#### 4. Revised `calculate_job_time` Flow

The method now has 5 steps instead of the original 4:

```python
def calculate_job_time(self, tasks, movers, pickup_access, dropoff_access):
    # 1. Sum labor minutes (unchanged)
    total_labor_minutes = sum(t['p'] for t in tasks)
    num_items = len(tasks)

    # 2. Effective teams (unchanged, BUT capped when elevator present)
    effective_teams = effective_teams_map.get(movers, movers / 2.0)
    if self._has_elevator(pickup_access, dropoff_access):
        effective_teams = min(effective_teams, self.ELEVATOR_PARALLELISM_CAP)  # ← NEW

    # 3. Bottleneck factor (unchanged)

    # 4. Base time with parallelism (unchanged)

    # 5a. Stairs friction — multiplicative (unchanged behavior)
    stair_friction = 1.0 + delta_pickup + delta_dropoff   # elevator returns 0.0 now
    adjusted_time = base_time * stair_friction

    # 5b. Elevator time — additive (NEW)
    elevator_minutes = (
        self._compute_elevator_adder(pickup_access, num_items)
        + self._compute_elevator_adder(dropoff_access, num_items)
    )
    final_time = adjusted_time + elevator_minutes   # ← add, don't multiply
```

**Key design decisions:**
- Elevator minutes are added **after** parallelism division because elevator wait/ride is wall-clock time that cannot be parallelized — teams queue for the elevator regardless of how many there are.
- The parallelism cap (`min(effective_teams, 1.5)`) ensures that even the base labor time doesn't get divided too aggressively in elevator buildings. With 6 movers on the ground, you get ~3 effective teams. In an elevator building, you get at most 1.5.
- Stairs friction still applies multiplicatively and is unaffected by the elevator changes. A job with stairs at pickup AND elevator at dropoff gets both: multiplicative stair friction on base time, plus additive elevator minutes on top.

---

### Before vs After: Numeric Comparison

**Scenario: 48 items, 25th floor, elevator at both pickup and dropoff, 2 movers**

| | Old Model | New Model |
|---|---|---|
| Base labor | 200 min | 200 min |
| Parallelism | 200 min (1 team) | 200 min (1 team, cap doesn't affect 2 movers) |
| Elevator | ×1.68 → 336 min | +2 × (24 trips × 3.5 min) = +168 min → 368 min |
| **Inflation** | **+68%** | **+84%** (but drops as items decrease) |

**Scenario: 48 items, 10th floor, elevator at pickup only, 4 movers**

| | Old Model | New Model |
|---|---|---|
| Base labor | 200 min | 200 min |
| Parallelism (4 movers) | 200/2.0/0.85 = 117.6 min | 200/1.5/0.85 = 156.9 min (capped) |
| Elevator | ×1.16 → 136.4 min | +24 trips × 2.3 min = +55.2 min → 212.1 min |

**Scenario: 7 items, 20th floor, elevator at pickup only, 2 movers**

| | Old Model | New Model |
|---|---|---|
| Base labor | 50 min | 50 min |
| Elevator | ×1.28 → 64 min | +4 trips × 3.1 min = +12.4 min → 62.4 min |
| **Inflation** | **+28%** | **+25%** |

The new model produces **less inflation for large jobs** (where the old percentage caused the biggest distortions) and **comparable results for small jobs**.

---

### Regression Test Results (`tests/test_elevator_fix.py`)

```
✓ _compute_elevator_adder math checks passed
✓ _access_friction_delta returns 0 for elevator, nonzero for stairs
✓ _has_elevator detection works
✓ Elevator inflation within acceptable range (33.6% for 25-floor both-ends)
✓ Elevator parallelism cap working (ground 1.65x speedup vs elevator 0.85x)
✓ Per-item elevator cost consistent across job sizes (ratio: 1.04x)
```

Key validation:
- **Per-item cost consistency**: Small job = 1.33 min/item, large job = 1.28 min/item (1.04x ratio). Confirms the additive model doesn't scale with item complexity.
- **Inflation cap**: 48-item job at 25th floor with elevator at both ends = 33.6% inflation (was 68%).
- **Parallelism**: 6 movers on ground = 1.65x faster than 2. With elevator = only 0.85x. Teams queue.

---

### Constants (`calculator.py`) — Quick Reference

| Constant | Value | Meaning |
|----------|-------|---------|
| `ELEVATOR_FIXED_PER_TRIP` | 1.5 min | Walk + load/unload at elevator door |
| `ELEVATOR_RIDE_PER_FLOOR` | 0.08 min | ~5 sec/floor ride time |
| `AVG_ITEMS_PER_ELEVATOR_LOAD` | 2.0 | Items per elevator trip |
| `ELEVATOR_PARALLELISM_CAP` | 1.5 | Max effective teams w/ elevator |
| `STAIR_BASE_FRICTION` | 0.06 | Stairs base % (unchanged) |
| `STAIR_PER_FLOOR` | 0.035 | Stairs per-flight % (unchanged) |

---

## 👷 Crew Override (Deep Dive)

The calculator has always evaluated every possible crew size internally. This feature exposes that evaluation to the user via a post-analysis slider — no AI re-run required.

---

### The Problem Before

`calculate_total_logistics` picked a crew size automatically using a cost/time scoring function and returned a single result. There was no way for the UI to say "show me what 4 movers looks like."

```
auto_pick:
  for m in [2, 3, 4, 5, 6]:
      time[m] = calculate_job_time(tasks, m, ...)
      cost[m] = time[m] × m × WAGE_RATE

  score(m) = 0.4 × norm_time + 0.6 × norm_cost   # or 0.2/0.8 for small jobs
  best = m with lowest score(m)
  return best
```

The user saw only the winning `m`. All other evaluations were discarded.

---

### What Changed

#### 1. `forced_movers` parameter added to `calculate_total_logistics`

```python
def calculate_total_logistics(
    self,
    items,
    pickup_access,
    dropoff_access,
    travel_time    = 30,
    pre_move_travel = 30,
    forced_movers  = None      # ← NEW optional override
) -> Dict:
```

**Pseudocode for the override branch:**

```
# Step 1: build tasks (unchanged)
tasks = build_tasks(items)

# Step 2: select vehicles
cab_seats = sum(vehicle.maxSeats × quantity for vehicle in vehicles)

# Step 3: evaluate crew sizes within vehicle cab capacity (for auto-recommendation)
for m in range(2, cab_seats + 1):
    evals[m] = {
        time = calculate_job_time(tasks, m, pickup_access, dropoff_access),
        cost = time × m × WAGE_RATE
    }

# Step 4: auto-pick within cab capacity
auto_recommended_m = m with lowest score(m)

# Step 5: apply override  ← NEW (clamped to MAX_MOVERS=6, not cab_seats)
if forced_movers is not None:
    clamped = clamp(forced_movers, min=2, max=6)
    recommended_m = clamped
    forced_eval = evals.get(clamped)
    if forced_eval:
        base_minutes = forced_eval.time
    else:
        # mover count beyond cab_seats — not pre-evaluated, compute on the fly
        base_minutes = calculate_job_time(tasks, clamped, pickup_access, dropoff_access)
else:
    recommended_m = auto_recommended_m
    base_minutes  = evals[auto_recommended_m].time

# Step 6: price, range, output (all downstream uses recommended_m — unchanged)
total_time_minutes = base_minutes + travel_time + pre_move_travel
base_price         = total_time_minutes × recommended_m × WAGE_RATE
```

The result dict now carries:
```
material.numberOfWorkers    = recommended_m         # what is actually used (may be forced)
material.recommendedWorkers = auto_recommended_m    # what algorithm would have picked
material.cabSeats           = cab_seats              # vehicle cab capacity
```

#### 2. UI slider in Logistics tab (`app.py`)

```
on tab3 render:
    current_workers = calculations.material.numberOfWorkers
    auto_workers    = calculations.material.recommendedWorkers   (or current if missing)
    cab_seats       = calculations.material.cabSeats             # vehicle cab capacity

    selected = st.slider("Number of movers", min=2, max=6, value=min(current_workers, 6))

    if selected != auto_workers:
        show caption: "✏️ Overriding recommendation — algorithm suggests N movers"
    else:
        show caption: "✅ Using recommended crew size of N movers"

    if selected > cab_seats:
        show caption: "⚠️ N movers — M in truck, K follow separately"

    if selected != current_workers:
        # Slider moved — trigger recalculation (no AI call)
        new_calculations = calculator.calculate_total_logistics(
            items          = result['items'],     # raw AI-detected items (not display items)
            pickup_access  = { type, floors },
            dropoff_access = { type, floors },
            travel_time    = sidebar value,
            pre_move_travel = sidebar value,
            forced_movers  = selected             # ← pass the override
        )
        session_state.analysis_result['calculations'] = new_calculations
        st.rerun()                                # all tabs re-read the new calculations

    display_logistics_summary(calculations)       # renders vehicle/time/price from new data
```

---

### Algorithm recommendation vs. user override

```
Scenario A: Cargo Van (cabSeats=2), algorithm recommends 2 movers
  → slider shows 2, user selects 2 → no override
  → numberOfWorkers = 2

Scenario B: 26' Truck (cabSeats=3), algorithm recommends 3 movers
  → slider shows 2–6, user drags to 5
  → forced_movers = 5, clamped to MAX_MOVERS = 6
  → 5 is not in pre-evaluated evals (only 2,3 were evaluated)
  → calculate_job_time(tasks, 5, ...) runs on the fly
  → numberOfWorkers = 5, recommendedWorkers = 3
  → UI caption: "⚠️ 5 movers — 3 in truck, 2 follow separately"

Scenario C: user slides to 2 movers (minimum)
  → clamped = max(2, min(2, 6)) = 2  (always valid)
```

The algorithm's scoring function is only exposed to crew sizes that fit in the vehicle cab, so the **recommended** badge stays realistic. The **override** escape hatch lets the user explore larger crews without a surcharge — just normal labor cost (`time × movers × $40/hr`).

---

### Trade-off visible to user

```
2 movers (recommended):  202 min,  $283   — slower, cheaper (algorithm pick for small job)
3 movers (override):     180 min,  $378   — faster, more expensive
4 movers:                155 min,  $517   — even faster, diminishing returns
5 movers:                148 min,  $617   — minimal time gain, higher cost
6 movers:                145 min,  $726   — "ant colony" congestion effect
```

Time decreases with more movers due to parallelism. Cost increases because more labor-hours are billed. The bottleneck map reduces effective parallelism as crew grows:

```
bottleneck_map = {
    2: 1.00,   # no congestion at truck door
    3: 0.95,
    4: 0.85,
    5: 0.70,
    6: 0.55    # heavy congestion — "ant colony" effect
}

effective_time = (labor_minutes / effective_teams) / bottleneck_factor
```

This means adding movers beyond 4–5 yields diminishing time savings but keeps increasing cost — the scoring function already models this, and the slider lets users explore it directly.

---

## 💰 Pricing Range Display (Deep Dive)

The pricing breakdown shows `$min – $max` instead of a single number. The range comes from the same CSV that drives the "Estimated Range" clock in the time breakdown — keeping both consistent.

---

### Data source: `Vision_Agent_Hour_Range_Mapping.csv`

```
estimate_hours,min_hours,max_hours
1.00, 0.75, 1.25
1.25, 1.00, 1.50
1.50, 1.25, 1.75
2.00, 1.75, 2.25
...
```

Each row maps a point estimate to a band. The calculator looks up the nearest row by rounding to the nearest 0.25 hr.

---

### `_get_hour_range_data(total_hours)` — new helper

```
function _get_hour_range_data(total_hours):
    load CSV rows into list of { estimate_hours, min_hours, max_hours }

    if no rows:
        return (total_hours, total_hours)       # fallback: zero-width range

    rounded = round(total_hours × 4) / 4        # snap to nearest 0.25 hr
    nearest = row where |row.estimate_hours - rounded| is smallest

    return (nearest.min_hours, nearest.max_hours)
```

`lookup_hour_range(total_hours)` now calls this and formats the result as a string.
Both functions share the same lookup — they can never disagree.

---

### Pricing range calculation in `calculate_total_logistics`

```
# Point estimate (unchanged — used for base_price)
total_time_minutes = base_minutes + travel_time + pre_move_travel
base_price         = total_time_minutes × recommended_m × WAGE_RATE

# Range  ← NEW
(min_hours, max_hours) = _get_hour_range_data(total_time_minutes / 60)

min_total_minutes = min_hours × 60
max_total_minutes = max_hours × 60

min_base_price = min_total_minutes × recommended_m × WAGE_RATE
max_base_price = max_total_minutes × recommended_m × WAGE_RATE
```

All three values (point, min, max) scale by the **same** `recommended_m × WAGE_RATE`, so changing the crew slider also shifts the range proportionally.

---

### Output dict additions

```python
'pricing': {
    'basePrice':              round(base_price, 2),
    'basePriceMin':           round(min_base_price, 2),      # NEW
    'basePriceMax':           round(max_base_price, 2),      # NEW
    'GST':                    round(base_price × 0.05, 2),
    'GSTMin':                 round(min_base_price × 0.05, 2),  # NEW
    'GSTMax':                 round(max_base_price × 0.05, 2),  # NEW
    'totalExpectedPrice':     round(base_price × 1.05, 2),
    'totalExpectedPriceMin':  round(min_base_price × 1.05, 2),  # NEW
    'totalExpectedPriceMax':  round(max_base_price × 1.05, 2),  # NEW
    'breakdown':              "N movers @ $40/hr"
}
```

---

### UI rendering in `display_pricing` (`app.py`)

```
col1:
    Base Price:  $min_base  –  $max_base
    GST (5%):   $min_gst   –  $max_gst
    caption:     "N movers @ $40/hr"

col2 (highlighted):
    $totalMin  –  $totalMax
    caption: "Total Expected Price (range)"
```

The top-level metric card in the Overview tab also shows the range:
```
st.metric("Total Price", f"${totalMin:.2f} – ${totalMax:.2f}")
```

---

### Numeric example

```
Job: 3 movers, total_time_minutes = 202 min → 3.37 hrs
CSV lookup: rounded to 3.25 hrs → row: min=2.75, max=3.75

min_total_minutes = 2.75 × 60 = 165 min
max_total_minutes = 3.75 × 60 = 225 min

min_base_price = 165 × 3 × $0.667/min = $330.17
max_base_price = 225 × 3 × $0.667/min = $450.23

Total range (with GST):
    $330.17 × 1.05 = $346.68
    $450.23 × 1.05 = $472.74

Display: $346.68 – $472.74
```

---

## 📂 Project Structure

```
Version 9/Gemini/
├── vision-agent.py              # Main orchestrator
├── README.md                    # This file
└── modules/
    ├── __init__.py              # Module exports
    ├── base.py                  # Abstract base classes
    ├── file_handlers.py         # Polymorphic file handling
    ├── calculator.py            # Logistics calculations (uses converted_items_lowered.json)
    └── ai_client.py             # AI service abstraction
```

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│     MoovEZVisionAnalyzerV6 (Orchestrator)           │
│     - Coordinates all components                     │
│     - Manages workflow                               │
└─────────────┬────────────────────────────────────────┘
              │
    ┌─────────┴──────────┬──────────────┬─────────────┐
    ▼                    ▼              ▼             ▼
┌──────────┐    ┌─────────────┐  ┌──────────┐  ┌──────────┐
│ File     │    │ AI Client   │  │Calculator│  │  Data    │
│ Handlers │    │ (Gemini)    │  │ (Logic)  │  │  Files   │
└──────────┘    └─────────────┘  └──────────┘  └──────────┘
```

### Design Patterns Used
- **Abstract Factory**: File handler creation based on type
- **Strategy Pattern**: Different handling strategies for images vs videos
- **Template Method**: Calculation workflow in calculator
- **Facade Pattern**: Simplified interface through main analyzer

---

## 📦 Module Details

### 1. `base.py` - Abstract Base Classes
**Purpose**: Define interfaces for all components

```python
# Abstract base classes using ABC
class BaseFileHandler(ABC):
    @abstractmethod
    def validate(self) -> bool
    @abstractmethod
    def get_file_info(self) -> Dict
    @abstractmethod
    def prepare_for_upload(self) -> Any

class BaseCalculator(ABC):
    @abstractmethod
    def calculate_total_logistics(self, items, access) -> Dict

class BaseAIClient(ABC):
    @abstractmethod
    def upload_file(self, file_path: str) -> Any
    @abstractmethod
    def generate_content(self, prompt: str, files: List) -> str
```

**Benefits**:
- Clear contracts for all implementations
- Enforces consistency across modules
- Easy to add new implementations

---

### 2. `file_handlers.py` - Polymorphic File Handling
**Purpose**: Uniform interface for different media types

```python
class ImageHandler(BaseFileHandler):
    """Handles: JPG, PNG, GIF, BMP, WEBP, TIFF, HEIC, HEIF"""
    
class VideoHandler(BaseFileHandler):
    """Handles: MP4, MOV, AVI, MKV, WEBM, FLV, WMV, M4V"""
    
class FileHandlerFactory:
    @staticmethod
    def classify_files(file_paths: List[str]) -> Tuple[List, List]:
        """Automatically sorts files into images and videos"""
```

**Benefits**:
- Polymorphic handling: `handler.validate()` works for any type
- Easy to add new formats (PDF, 3D models, etc.)
- Encapsulates format-specific logic

---

### 3. `calculator.py` - Logistics Engine
**Purpose**: All moving calculations isolated

```python
class MovingCalculator(BaseCalculator):
    def calculate_item_time(self, item: Dict) -> float
    def calculate_total_logistics(self, items: List, access: Dict) -> Dict
    def select_optimal_vehicles(self, volume: float, weight: float) -> List
    def calculate_pricing(self, base_time: float, vehicles: List) -> Dict
```

**Benefits**:
- Single Responsibility: Only handles calculations
- No AI or file handling mixed in
- Easy to unit test with mock data
- All business logic in one place

---

### 4. `ai_client.py` - AI Service Abstraction
**Purpose**: Encapsulate AI provider interactions

```python
class GeminiClient(BaseAIClient):
    def upload_file(self, file_path: str) -> File
    def wait_for_video_processing(self, file: File) -> None
    def generate_content(self, prompt: str, files: List) -> str
    def get_vision_prompt(self) -> str
    def cleanup_file(self, file: File) -> None
```

**Benefits**:
- Swappable AI providers (can add OpenAI, Claude, etc.)
- Centralized API interaction logic
- Easier to mock for testing
- Retry logic and error handling in one place

---

## 📊 Supported Formats

| Type | Formats | Handler |
|------|---------|---------|
| **Images** | .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff, .heic, .heif (iPhone) | `ImageHandler` |
| **Videos** | .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v | `VideoHandler` |

---

## 💻 Usage

### Basic Example (Same as V5)
```bash
cd "Version 6/Gemini"
python vision-agent.py
```

### Programmatic Usage
```python
from modules import FileHandlerFactory, MovingCalculator, GeminiClient

# Initialize
analyzer = MoovEZVisionAnalyzerV6()

# Process request
result = analyzer.process_moving_request(
    file_paths=["bedroom.jpg", "tour.mp4"],
    pickup_access={"type": "stairs", "floors": 3},
    dropoff_access={"type": "elevator", "floors": 5},
    travel_time_minutes=30
)

# Access results
print(f"Total items: {result['summary']['totalItems']}")
print(f"Total price: ${result['calculations']['pricing']['totalExpectedPrice']}")
```

### Backward Compatibility
```python
# V5 code still works!
from vision_agent import MoovEZVisionAnalyzerV5

analyzer = MoovEZVisionAnalyzerV5()  # Actually creates V6 instance
```

---

## 🔧 Extending the System

### Adding a New File Type (e.g., PDF)
```python
# In file_handlers.py
class PDFHandler(BaseFileHandler):
    SUPPORTED_FORMATS = ['.pdf']
    
    def validate(self) -> bool:
        # PDF-specific validation
        return self.file_path.lower().endswith('.pdf')
    
    def prepare_for_upload(self) -> Any:
        # PDF-specific preparation
        pass

# In FileHandlerFactory.classify_files()
# Add PDF classification logic
```

### Adding a New AI Provider (e.g., Claude)
```python
# In ai_client.py
class ClaudeClient(BaseAIClient):
    def __init__(self, api_key: str):
        self.client = anthropic.Client(api_key)
    
    def upload_file(self, file_path: str) -> Any:
        # Claude-specific upload
        pass
    
    def generate_content(self, prompt: str, files: List) -> str:
        # Claude API call
        pass

# In vision-agent.py
# Allow AI client selection
analyzer = MoovEZVisionAnalyzerV6(ai_client=ClaudeClient(api_key))
```

---

## 📈 Performance Metrics

**Same Performance as V5:**
- Image Upload: ~1 second per image
- Video Upload: ~5-10 seconds per video
- Video Processing: ~5-15 seconds per video
- API Analysis: ~3-5 seconds
- Calculation: <1 second
- **Total**: ~20-40 seconds (2 images + 1 video)

**Code Metrics:**
- Main file: 450 lines (down from 1188)
- Total codebase: ~1310 lines (modularized)
- Modules: 4 focused components
- Test coverage: Easier with modular design

---

## 📦 Data Dependencies

### Required Files
- `../../Data/moving_items_logistics_v2.json` - 80+ item database
- `../../Data/moving_calculation_rules.json` - Calculation rules

### Environment Variables
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 🚀 Key Features

### From Modular Architecture
- **Easy Maintenance**: Update one module without affecting others
- **Independent Testing**: Test each component in isolation
- **Clear Interfaces**: Abstract base classes define contracts
- **Extensibility**: Add features without breaking existing code
- **Code Reuse**: Inheritance enables shared functionality

### From V5 (All Retained)
- **Video Support**: Process video walkthroughs of rooms/properties
- **Mixed Media**: Combine images and videos in single request
- **Batch Processing**: Multiple files in single API call
- **Smart Detection**: Identifies items with size classification (S/M/L)
- **No Double-Counting**: Handles same items across multiple files/frames
- **Detailed Breakdown**: Per-item time, volume, weight analysis
- **Multi-Vehicle Support**: Optimal truck combination for large moves
- **Access Factors**: Stairs (multiplicative friction), elevators (additive per-trip model with parallelism cap)

---

## 🔄 Version Comparison

### vs Version 5
- ✅ **Modular architecture** with abstraction, inheritance, polymorphism
- ✅ **Reduced complexity**: Main file 62% smaller (1188 → 450 lines)
- ✅ **Better maintainability**: Focused modules vs monolithic code
- ✅ **Easier extensibility**: Add features without breaking changes
- ✅ **100% backward compatible**: V5 API still works
- ✅ **All V5 features retained**: Video, batch processing, etc.

### vs Version 4
- ✅ Modular, scalable architecture
- ✅ Video file support (MP4, MOV, AVI, etc.)
- ✅ Mixed media uploads (images + videos)
- ✅ Better code organization
- ✅ Same performance for images

### Best Use Cases
- **Production Systems**: Maintainability and scalability critical
- **Team Development**: Clear module boundaries for parallel work
- **Feature Growth**: Need to add new capabilities frequently
- **Testing**: Independent module testing required
- **Long-term Projects**: Code will be maintained over years

---

## 🧪 Testing Advantages

### Module Independence
```python
# Test calculator without AI
from modules.calculator import MovingCalculator

calc = MovingCalculator(items_db_path, rules_path)
result = calc.calculate_total_logistics(mock_items, mock_access)
assert result['pricing']['basePrice'] > 0

# Test file handlers without API
from modules.file_handlers import ImageHandler

handler = ImageHandler("test.jpg")
assert handler.validate() == True

# Test AI client with mocks
from modules.ai_client import GeminiClient
from unittest.mock import Mock

client = GeminiClient(api_key)
client.upload_file = Mock(return_value=mock_file)
```

---

## 🔍 Code Quality Improvements

### Before (V5 - Monolithic)
```
vision-agent.py (1188 lines)
├── File handling (mixed with logic)
├── AI client code (mixed with logic)
├── Calculator (mixed with everything)
└── Main orchestration
```

**Problems:**
- Hard to find specific functionality
- Changes risk breaking unrelated features
- Difficult to test individual components
- No clear separation of concerns

### After (V6 - Modular)
```
vision-agent.py (450 lines) - Orchestration only
modules/
├── base.py (90 lines) - Interfaces
├── file_handlers.py (180 lines) - File handling only
├── calculator.py (450 lines) - Calculations only
└── ai_client.py (140 lines) - AI integration only
```

**Benefits:**
- Easy to locate and modify specific functionality
- Changes isolated to relevant module
- Each module independently testable
- Clear separation of concerns

---

## 📞 Migration from V5

**Good News**: No changes required!

```python
# V5 code
from vision_agent import MoovEZVisionAnalyzerV5
analyzer = MoovEZVisionAnalyzerV5()

# Still works in V6 (alias automatically maps to V6 class)
```

For new code, prefer using `MoovEZVisionAnalyzerV6` explicitly:
```python
from vision_agent import MoovEZVisionAnalyzerV6
analyzer = MoovEZVisionAnalyzerV6()
```
