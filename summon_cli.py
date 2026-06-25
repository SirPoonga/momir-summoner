#!/usr/bin/env python3
"""Momir command-line tester for summoning, printing, and library tracking."""
import argparse
from db import (
    connect,
    card_count,
    printed_card_count,
    total_print_count,
    random_card,
    get_card,
    mark_summoned,
    mark_printed,
    unmark_printed,
    mana_values,
    search_cards,
    reset_printed,
    owned_cards,
    missing_cards,
    progress_by_mana_value,
)
from render_printer import render_printer, print_printer, render_printer_back


def show_card(card):
    owned = int(card.get("printed_count") or 0) > 0
    status = "In library" if owned else "Not in library yet"
    pt = ""
    if card.get("power") or card.get("toughness"):
        pt = f"{card.get('power','?')}/{card.get('toughness','?')}"
    print(f"\n{card['name']}")
    print(f"MV {card['mana_value']} | {card.get('type_line') or ''} {pt}")
    print(status)
    print(f"File under: {card.get('storage_letter') or card['name'][:1].upper()}")
    if card.get("oracle_text"):
        print("-" * 40)
        print(card["oracle_text"])



def find_card_by_name(conn, name):
    rows = search_cards(conn, name, 50)
    exact = [r for r in rows if r["name"].lower() == name.lower()]
    if exact:
        return exact[0]
    if len(rows) == 1:
        return rows[0]
    if not rows:
        print("Card not found.")
        return None
    print("Multiple matches. Use the exact name or card id:")
    for r in rows[:20]:
        print(f"{r['id']} | {r['name']} | MV {r['mana_value']}")
    return None


def add_name_commands(sub):
    p = sub.add_parser("print-name")
    p.add_argument("name")
    p.add_argument("--printer-address", default=None)

    p = sub.add_parser("printer-print-name")
    p.add_argument("name")
    p.add_argument("--printer-address", default=None)

    p = sub.add_parser("printer-render-name")
    p.add_argument("name")

    p = sub.add_parser("print-last")
    p.add_argument("--printer-address", default=None)


def main():
    parser = argparse.ArgumentParser(description="Momir CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats")

    p_summon = sub.add_parser("summon")
    p_summon.add_argument("cmc", type=int)
    p_summon.add_argument("--mark-printed", action="store_true", help="mark the selected card as owned/printed")
    p_summon.add_argument("--own", action="store_true", help="same as --mark-printed")
    p_summon.add_argument("--printer-render", action="store_true", help="render a configured printer 2x3 JPG")
    p_summon.add_argument("--printer-print", action="store_true", help="render and send to configured printer over Bluetooth OBEX")
    p_summon.add_argument("--printer-address", default=None, help="override the locally configured Bluetooth printer address")

    p_search = sub.add_parser("search")
    p_search.add_argument("term")

    p_printed = sub.add_parser("mark-printed")
    p_printed.add_argument("card_id")

    p_own = sub.add_parser("own")
    p_own.add_argument("card_id")

    p_unown = sub.add_parser("unown")
    p_unown.add_argument("card_id")

    p_owned = sub.add_parser("owned")
    p_owned.add_argument("letter", nargs="?", help="optional storage letter, like A or L")
    p_owned.add_argument("--compact", action="store_true")

    p_missing = sub.add_parser("missing")
    p_missing.add_argument("cmc", nargs="?", type=int)
    p_missing.add_argument("--limit", type=int, default=100)

    sub.add_parser("progress")


    p_printer_render = sub.add_parser("printer-render")
    p_printer_render.add_argument("card_id")

    p_back = sub.add_parser("print-back")
    p_back.add_argument("--printer-address", default=None)

    p_printer_print = sub.add_parser("printer-print")
    p_printer_print.add_argument("card_id")
    p_printer_print.add_argument("--printer-address", default=None)

    add_name_commands(sub)

    p_reset = sub.add_parser("reset-printed")
    p_reset.add_argument("--history", action="store_true", help="also clear printed flags in summon_history")
    p_reset.add_argument("--yes", action="store_true", help="required confirmation")


    args = parser.parse_args()
    conn = connect()

    if args.cmd == "stats":
        print(f"Cards in database: {card_count(conn)}")
        print(f"Cards owned/printed: {printed_card_count(conn)}")
        print("Mana values:", ", ".join(map(str, mana_values(conn))))
        return

    if args.cmd == "summon":
        card = random_card(conn, args.cmc)
        if not card:
            print(f"No creature found for CMC {args.cmc}")
            return
        history_id = mark_summoned(conn, card["id"], args.cmc)
        show_card(card)
        print(f"\ncard_id: {card['id']}")
        print(f"history_id: {history_id}")
        if args.printer_render or args.printer_print:
            out = render_printer(card)
            print(f"Rendered printer image: {out}")
        if args.printer_print:
            if not print_printer(out, args.printer_address):
                print("Print failed; card was NOT marked as owned.")
                return
            print("Sent to configured printer.")
            mark_printed(conn, card["id"], history_id)
            print("Marked as owned.")
            return
        if args.mark_printed or args.own:
            mark_printed(conn, card["id"], history_id)
            print("Marked as owned.")
        return

    if args.cmd == "search":
        for card in search_cards(conn, args.term, 25):
            owned = "owned" if int(card.get("printed_count") or 0) > 0 else "not owned"
            print(f"{card['id']} | {card['name']} | MV {card['mana_value']} | {owned} | file {card['storage_letter']}")
        return

    if args.cmd in {"print-name", "printer-print-name", "printer-render-name"}:
        card = find_card_by_name(conn, args.name)
        if not card:
            return
        show_card(card)
        out = render_printer(card)
        print(f"Rendered printer image: {out}")
        if args.cmd in {"print-name", "printer-print-name"}:
            if not print_printer(out, args.printer_address):
                print("Print failed; card was NOT marked as owned.")
                return
            mark_printed(conn, card["id"])
            print("Sent to configured printer and marked as owned.")
        return


    if args.cmd == "print-last":
        row = conn.execute(
            """
            SELECT c.*, h.id AS history_id
            FROM summon_history h
            JOIN cards c ON c.id = h.card_id
            ORDER BY h.id DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            print("No summon history found.")
            return
        card = dict(row)
        show_card(card)
        out = render_printer(card)
        print(f"Rendered printer image: {out}")
        if not print_printer(out, args.printer_address):
            print("Print failed; card was NOT marked as owned.")
            return
        mark_printed(conn, card["id"], card.get("history_id"))
        print("Sent to configured printer and marked as owned.")
        return

    if args.cmd in {"mark-printed", "own"}:
        mark_printed(conn, args.card_id)
        print("Marked as owned.")
        return

    if args.cmd == "unown":
        unmark_printed(conn, args.card_id)
        print("Removed from owned library.")
        return

    if args.cmd == "owned":
        cards = owned_cards(conn, args.letter)
        print(f"Owned creatures: {len(cards)}")
        if args.compact:
            for card in cards:
                print(card["name"])
            return
        current = None
        for card in cards:
            letter = card.get("storage_letter") or "#"
            if letter != current:
                current = letter
                print(f"\n{current}")
            print(f"  {card['name']} | MV {card['mana_value']}")
        return

    if args.cmd == "missing":
        cards = missing_cards(conn, args.cmc, args.limit)
        label = f"CMC {args.cmc}" if args.cmc is not None else "all mana values"
        print(f"Missing/unowned creatures for {label}: showing {len(cards)}")
        for card in cards:
            print(f"{card['name']} | MV {card['mana_value']} | file {card['storage_letter']}")
        return

    if args.cmd == "progress":
        total = card_count(conn)
        owned = printed_card_count(conn)
        pct = (owned / total * 100) if total else 0
        print("Momir Library Progress")
        print(f"Owned creatures: {owned}")
        print(f"Total creatures: {total}")
        print(f"Completion: {pct:.2f}%")
        print("\nBy mana value:")
        for row in progress_by_mana_value(conn):
            mv = row["mana_value"]
            row_owned = row["owned"] or 0
            row_total = row["total"] or 0
            print(f"MV {mv:<2} {row_owned}/{row_total}")
        return


    if args.cmd == "printer-render":
        card = get_card(conn, args.card_id)
        if not card:
            print("Card not found.")
            return
        out = render_printer(card)
        print(f"Rendered printer image: {out}")
        return

    if args.cmd == "printer-print":
        card = get_card(conn, args.card_id)
        if not card:
            print("Card not found.")
            return
        out = render_printer(card)
        print(f"Rendered printer image: {out}")
        if not print_printer(out, args.printer_address):
            print("Print failed; card was NOT marked as owned.")
            return
        mark_printed(conn, card["id"])
        print("Sent to configured printer and marked as owned.")
        return

    if args.cmd == "print-back":
        out = render_printer_back()
        print(f"Rendered printer back image: {out}")
        if not print_printer(out, args.printer_address):
            print("Back print failed.")
            return
        print("Printed card back.")
        return

    if args.cmd == "reset-printed":
        if not args.yes:
            print("This clears all owned/printed status. Re-run with --yes to confirm.")
            return
        reset_printed(conn, reset_history=args.history)
        print("Owned/printed status cleared.")
        return



if __name__ == "__main__":
    main()
