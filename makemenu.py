import datetime
import json
import os
import random
import sys

my_folder = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))
options_folder = os.path.join(my_folder, 'options')
history_folder = os.path.join(my_folder, 'history')
days_of_week = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
filters = {
    "sun": ["+dessert", "-plain", "+extra", "-end-of-week"],
    "mon": ["-end-of-week"],
    "tue": ["-end-of-week"],
    "wed": ["+dessert", "-plain", "+extra", "-end-of-week"],
    "fri": ["+plain"]
}
min_repeat_days = 15
max_ago_relevant_day_count = 49
categories = ["+entree", "+dessert", "+extra"]


def load_folder(path, obj_name):
    items = []
    files = [fname for fname in os.listdir(path) if fname.endswith('.json')]
    for fname in files:
        with open(os.path.join(path, fname), 'rt') as f:
            txt = f.read()
        obj = json.loads(txt)
        obj['key'] = fname[:-5]
        items.append(obj)
    return items


def record(menu):
    menu_summary = {}
    for day in days_of_week:
        menu_summary[day] = [i.get("key") for i in menu[day]]

    fname = datetime.datetime.utcnow().isoformat()[:10] + '.json'
    with open(os.path.join(history_folder, fname), 'wt') as f:
        f.write(json.dumps(menu_summary, indent=2))
    cwd = os.getcwd()
    os.chdir(history_folder)
    try:
        os.system('git add %s && git commit -m "add weekly menu for %s" && git push' % (fname, fname[:-5]))
    finally:
        os.chdir(cwd)


def shop_for(item, shopping_list):
    ingredients = item.get('ingredients')
    if ingredients:
        for i in ingredients:
            reason = item["key"]
            if i in shopping_list:
                shopping_list[i].append(reason)
            else:
                shopping_list[i] = [reason]


def show_menu(menu):
    shopping_list = {}

    print('Menu\n----')
    for day in days_of_week:
        items = menu.get(day)
        if items:
            for item in items:
                if not item:
                    print('Unrecognized item on %s.' % day)
            line = day + ': ' + ', '.join([i.get("key") for i in items if i])
            print(line)
            for item in items:
                shop_for(item, shopping_list)
    return shopping_list


def show_shopping_list(shopping_list):
    print('\nShopping List\n-------------')
    ingredients = sorted(shopping_list.keys())
    for ingredient in ingredients:
        reasons = shopping_list[ingredient]
        print(ingredient + " (for %s)" % ' and '.join(reasons))


def has_tag(item, tag):
    return tag in item.get('tags', [])


def filter_options(options, filter):
    tag = filter[1:]
    should_have = bool(filter[0] == '+')
    return [o for o in options if has_tag(o, tag) == should_have]


def get_recency_score(event_date, today):
    ago = event_date - today
    # Don't give any score to items that have occured in previous 6 weeks
    n = min(ago.days, max_ago_relevant_day_count) if ago.days > min_repeat_days else 0
    return n * n


def weight_by_history(candidates, history):
    now = datetime.datetime.now()
    cumulative = 0
    weighted = []
    for c in candidates:
        # Assume this item has never been used in a menu before. That would give it
        # a maximum score.
        score = max_ago_relevant_day_count * max_ago_relevant_day_count
        # Now look to see how recently it was used.
        for menu in history:
            found = False
            increment = 0
            for day in days_of_week:
                increment += 1
                if c["key"] in menu.get(day, []):
                    menu_date = datetime.datetime.fromisoformat(menu.get("key"))
                    score = get_recency_score(now, menu_date + datetime.timedelta(days=increment))
                    found = True
                    break
            if found:
                break
        weighted.append({"score": score, "candidate": c})
        cumulative += score
    # Introduce randomness among equally-scored items.
    random.shuffle(weighted)
    weighted.sort(key=lambda x: x.get("score"), reverse=True)
    return weighted, cumulative


def select_not_recent(candidates, history):
    weighted, cumulative = weight_by_history(candidates, history)
    # If we found any items with a positive score (meaning they were used
    # long enough ago to be interesting for ranking)...
    if cumulative:
        # We are trying to select something from the front 15% or so of the
        # exponential distribution -- something old, but not necessarily the
        # exact oldest thing.
        lambda_val = cumulative * 0.15
        # Don't ever select something from beyond the first 30% of the exponential
        # distrubution.
        required_score = min(random.expovariate(1 / lambda_val), lambda_val * 2)
        consumed_probability = 0
        for item in weighted:
            next = consumed_probability + item["score"]
            if next > required_score:
                return item["candidate"]
            consumed_probability = next
    # If we get here, there was nothing that met our criteria; just select
    # at random from among the least-recently-used items. (Selecting [0] is
    # random because we already shuffled items with the same score.)
    return weighted[0]["candidate"]


def get_filtered_candidates(options, category, filters_for_day, used):
    candidates = filter_options(options, category)
    other_cateogries = [c for c in categories if c != category]
    for f in filters_for_day:
        if f not in other_cateogries:
            candidates = filter_options(candidates, f)
    candidates = [c for c in candidates if c not in used]
    return candidates


def get_week_worth_of_suggestions(options, history):
    used_entrees = []
    used_extras = []
    used_desserts = []
    menu = {}
    for day in days_of_week:
        extra = dessert = None
        filters_for_day = filters.get(day, [])
        candidates = get_filtered_candidates(options, '+entree', filters_for_day, used_entrees)
        entree = select_not_recent(candidates, history)
        used_entrees.append(entree)
        menu[day] = [entree]
        if "+extra" in filters_for_day:
            candidates = get_filtered_candidates(options, '+extra', filters_for_day, used_extras)
            extra = select_not_recent(candidates, history)
            menu[day].append(extra)
        if "+dessert" in filters_for_day:
            candidates = get_filtered_candidates(options, '+dessert', filters_for_day, used_desserts)
            dessert = select_not_recent(candidates, history)
            menu[day].append(dessert)
    return menu


def suggest(options, history):
    while True:
        menu = get_week_worth_of_suggestions(options, history)
        shopping_list = show_menu(menu)
        sys.stdout.write('\nRecord menu for this week? ')
        answer = input()
        if answer.lower().startswith('y'):
            show_shopping_list(shopping_list)
            record(menu)
            break


def find_option(options, name):
    for item in options:
        if item.get("key") == name:
            return item


def show_later(options, history):
    selected = history[0]
    menu = {}
    for day in days_of_week:
        items = selected.get(day)
        if items:
            menu[day] = []
            for name in items:
                item = find_option(options, name)
                if item:
                    menu[day].append(item)
                else:
                    print('Unrecognized item "%s" on %s.' % (name, day))
    shopping_list = show_menu(menu)
    show_shopping_list(shopping_list)


def main():
    history = load_folder(history_folder, "menu")
    options = load_folder(options_folder, "item")
    history.sort(key=lambda x: x.get("key"), reverse=True)
    if len(sys.argv) > 1 and sys.argv[1].startswith('sho'):
        show_later(options, history)
    else:
        suggest(options, history)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n')
