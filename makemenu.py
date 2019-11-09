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
min_repeat_days = 21
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
        os.system('echo git add %s && git commit -m "add weekly menu for %s" && git push' % (fname, fname[:-5]))
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


def show(menu):
    shopping_list = {}

    print('Menu\n----')
    for day in days_of_week:
        items = menu[day]
        line = day + ': ' + ', '.join([i.get("key") for i in items])
        for item in items:
            shop_for(item, shopping_list)
        print(line)

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


def get_recency_score(event, history, this_week):
    last_use = datetime.datetime.fromisoformat(event.get("when"))
    ago = this_week - last_use
    # Don't give any score to items that have occured in previous 6 weeks
    n = max(ago.days, max_ago_relevant_day_count) if ago.days > min_repeat_days else 0
    return n * n


def weight_by_history(candidates, history):
    this_week = datetime.datetime.date(datetime.datetime.utcnow())
    cumulative = 0
    weighted = []
    for c in candidates:
        score = max_ago_relevant_day_count * max_ago_relevant_day_count
        for menu in history:
            for day in days_of_week:
                if c in menu.get(day, []):
                    score = get_recency_score(menu, history, this_week)
                    break
        weighted.append({"score": score, "candidate": c})
        cumulative += score
    random.shuffle(weighted)
    weighted.sort(key=lambda x: x.get("score"), reverse=True)
    return weighted, cumulative


def select_not_recent(candidates, history):
    weighted, cumulative = weight_by_history(candidates, history)
    lambda_val = cumulative * 0.3
    offset = random.expovariate(1 / lambda_val)
    required_score = cumulative - offset
    consumed_probability = 0
    for item in weighted:
        next = consumed_probability + item["score"]
        if next > required_score:
            return item["candidate"]
        consumed_probability = next
    return weighted[0]


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
        show(menu)
        sys.stdout.write('\nRecord menu for this week? ')
        answer = input()
        if answer.lower().startswith('y'):
            record(menu)
            break


def main():
    options = load_folder(options_folder, "item")
    history = load_folder(history_folder, "menu")
    history.sort(key=lambda x: x.get("key"), reverse=True)
    suggest(options, history)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n')
