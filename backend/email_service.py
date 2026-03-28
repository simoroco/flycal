import json
import logging
import socket
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from database import SessionLocal, Setting, Search, Flight, Airline, CrawlerLog, log_activity

logger = logging.getLogger("flycal.email")

DEFAULT_SERVER_IP = "192.168.1.50"


def _get_server_hostname(settings=None):
    """Get server hostname from settings, fallback to auto-detect, then default."""
    if settings:
        hostname = settings.get("server_hostname", "")
        if hostname:
            return hostname
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return DEFAULT_SERVER_IP


def _get_settings():
    db = SessionLocal()
    try:
        rows = db.query(Setting).all()
        settings = {}
        for row in rows:
            settings[row.key] = row.value
        return settings
    finally:
        db.close()


def send_test_email(settings=None):
    """Send a real test email using the recap template with placeholder data."""
    if settings is None:
        settings = _get_settings()

    host = settings.get("smtp_host", "") or ""
    port = int(settings.get("smtp_port", 587) or 587)
    user = settings.get("smtp_user", "") or ""
    password = settings.get("smtp_password", "") or ""
    to_email = settings.get("smtp_to", "") or ""

    if not host or not user or not to_email:
        raise ValueError("SMTP host, user and recipient are required")

    server_hostname = _get_server_hostname(settings)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #1a1a2e; color: #e8e8f0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: rgba(255,255,255,0.05); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.1);">
            <h1 style="color: #6c63ff;">✈ FlyCal — Email de test</h1>
            <p style="color: #00c864; font-size: 1.1rem; font-weight: 600;">✅ Configuration SMTP fonctionnelle !</p>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 16px 0;">
            <p><strong>Trajet:</strong> PARIS → MARRAKECH</p>
            <p><strong>Dates:</strong> 2026-01-01 — 2026-01-15</p>
            <p><strong>Type de vol:</strong> Aller-retour</p>
            <p><strong>Scan:</strong> Test</p>
            <p><strong>Vols directs trouvés:</strong> 0</p>
            <h2 style="color: #6c63ff;">Par compagnie</h2>
            <ul><li><em>Aucune donnée (email de test)</em></li></ul>
            <h2 style="color: #6c63ff;">Top 3 — Meilleurs prix (aller)</h2>
            <ul><li><em>Aucune donnée (email de test)</em></li></ul>
            <h2 style="color: #6c63ff;">Top 3 — Meilleurs prix (retour)</h2>
            <ul><li><em>Aucune donnée (email de test)</em></li></ul>
            <h2 style="color: #6c63ff;">Top 3 — Meilleures combinaisons (score vert)</h2>
            <ul><li><em>Aucune donnée (email de test)</em></li></ul>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p><a href="http://{server_hostname}:4444/" style="color: #6c63ff;">Ouvrir FlyCal →</a></p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "FlyCal [Test] — Vérification SMTP"
    msg["From"] = user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_email], msg.as_string())

    logger.info(f"Test email sent to {to_email}")
    _db = SessionLocal()
    try:
        log_activity(_db, "email", "sent", "Test email sent")
    finally:
        _db.close()


def send_crawl_recap(search_id: int):
    settings = _get_settings()

    if settings.get("smtp_send_enabled") != "true":
        logger.info("Email sending disabled, skipping recap.")
        return

    host = settings.get("smtp_host", "")
    port = int(settings.get("smtp_port", "587"))
    user = settings.get("smtp_user", "")
    password = settings.get("smtp_password", "")
    to_email = settings.get("smtp_to", "")

    if not host or not user or not to_email:
        logger.warning("SMTP not configured, skipping email.")
        return

    db = SessionLocal()
    try:
        search = db.query(Search).filter(Search.id == search_id).first()
        if not search:
            return

        flights = (
            db.query(Flight)
            .filter(Flight.search_id == search_id)
            .all()
        )

        # Determine scan type from crawler log
        last_log = db.query(CrawlerLog).filter(CrawlerLog.search_id == search_id).order_by(CrawlerLog.started_at.desc()).first()
        scan_type = last_log.triggered_by if last_log else "manual"
        scan_type_label = "Automatique" if scan_type == "auto" else "Manuel"
        server_hostname = _get_server_hostname(settings)

        airlines_map = {}
        for f in flights:
            airline = db.query(Airline).filter(Airline.id == f.airline_id).first()
            name = airline.name if airline else "Unknown"
            if name not in airlines_map:
                airlines_map[name] = {"outbound": [], "return": []}
            airlines_map[name][f.direction].append(f)

        outbound_flights = [f for f in flights if f.direction == "outbound"]
        return_flights = [f for f in flights if f.direction == "return"]

        top_outbound = sorted(outbound_flights, key=lambda f: f.price)[:3]
        top_return = sorted(return_flights, key=lambda f: f.price)[:3]

        ideal_price = float(settings.get("ideal_price", "40"))
        time_slots = []
        try:
            time_slots = json.loads(settings.get("time_slots", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

        def get_time_color(departure_time_str):
            try:
                parts = departure_time_str.split(":")
                h = int(parts[0])
                m = int(parts[1]) if len(parts) > 1 else 0
                t_minutes = h * 60 + m
                for slot in time_slots:
                    sh, sm = map(int, slot["start"].split(":"))
                    eh, em = map(int, slot["end"].split(":"))
                    s_min = sh * 60 + sm
                    e_min = eh * 60 + em
                    if e_min <= s_min:
                        if t_minutes >= s_min or t_minutes < e_min:
                            return slot["color"]
                    else:
                        if s_min <= t_minutes < e_min:
                            return slot["color"]
            except Exception:
                pass
            return "orange"

        def get_price_color(price):
            if price <= ideal_price * 0.8:
                return "green"
            elif price <= ideal_price * 1.2:
                return "orange"
            return "red"

        def composite_color(c1, c2):
            rank = {"green": 0, "orange": 1, "red": 2}
            r1, r2 = rank.get(c1, 1), rank.get(c2, 1)
            if r1 == 0 and r2 == 0:
                return "green"
            if r1 == 2 and r2 == 2:
                return "red"
            if (r1 == 2 and r2 == 1) or (r1 == 1 and r2 == 2):
                return "red"
            return "orange"

        def score_flight(f):
            tc = get_time_color(str(f.departure_time))
            pc = get_price_color(f.price)
            return composite_color(tc, pc)

        green_combos = []
        for out_f in outbound_flights:
            if score_flight(out_f) == "green":
                if search.trip_type == "roundtrip":
                    for ret_f in return_flights:
                        if score_flight(ret_f) == "green":
                            green_combos.append((out_f, ret_f, out_f.price + ret_f.price))
                else:
                    green_combos.append((out_f, None, out_f.price))
        green_combos.sort(key=lambda x: x[2])
        top_green = green_combos[:3]

        airline_summary = ""
        for name, dirs in airlines_map.items():
            airline_summary += f"<li><strong>{name}</strong>: {len(dirs['outbound'])} aller, {len(dirs['return'])} retour</li>"

        top_outbound_html = ""
        for f in top_outbound:
            airline = db.query(Airline).filter(Airline.id == f.airline_id).first()
            aname = airline.name if airline else "?"
            top_outbound_html += (
                f"<li>{aname} — {f.flight_date} {f.departure_time}→{f.arrival_time} "
                f"({f.origin_airport}→{f.destination_airport}) — <strong>{f.price:.0f}€</strong></li>"
            )

        top_return_html = ""
        for f in top_return:
            airline = db.query(Airline).filter(Airline.id == f.airline_id).first()
            aname = airline.name if airline else "?"
            top_return_html += (
                f"<li>{aname} — {f.flight_date} {f.departure_time}→{f.arrival_time} "
                f"({f.origin_airport}→{f.destination_airport}) — <strong>{f.price:.0f}€</strong></li>"
            )

        top_green_html = ""
        for out_f, ret_f, total in top_green:
            airline_out = db.query(Airline).filter(Airline.id == out_f.airline_id).first()
            aname_out = airline_out.name if airline_out else "?"
            line = f"<li>Aller: {aname_out} {out_f.flight_date} {out_f.departure_time}→{out_f.arrival_time} ({out_f.price:.0f}€)"
            if ret_f:
                airline_ret = db.query(Airline).filter(Airline.id == ret_f.airline_id).first()
                aname_ret = airline_ret.name if airline_ret else "?"
                line += f" + Retour: {aname_ret} {ret_f.flight_date} {ret_f.departure_time}→{ret_f.arrival_time} ({ret_f.price:.0f}€)"
            line += f" — <strong>Total: {total:.0f}€</strong></li>"
            top_green_html += line

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #1a1a2e; color: #e8e8f0; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: rgba(255,255,255,0.05); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.1);">
                <h1 style="color: #6c63ff;">✈ FlyCal — Résumé du crawl ({scan_type_label})</h1>
                <p><strong>Trajet:</strong> {search.origin_city} → {search.destination_city}</p>
                <p><strong>Dates:</strong> {search.date_from} — {search.date_to}</p>
                <p><strong>Type de vol:</strong> {"Aller-retour" if search.trip_type == "roundtrip" else "Aller simple"}</p>
                <p><strong>Scan:</strong> {scan_type_label}</p>
                <p><strong>Vols directs trouvés:</strong> {len(flights)}</p>
                <h2 style="color: #6c63ff;">Par compagnie</h2>
                <ul>{airline_summary}</ul>
                <h2 style="color: #6c63ff;">Top 3 — Meilleurs prix (aller)</h2>
                <ul>{top_outbound_html if top_outbound_html else "<li>Aucun vol aller trouvé</li>"}</ul>
                {"<h2 style='color: #6c63ff;'>Top 3 — Meilleurs prix (retour)</h2><ul>" + (top_return_html if top_return_html else "<li>Aucun vol retour trouvé</li>") + "</ul>" if search.trip_type == "roundtrip" else ""}
                <h2 style="color: #6c63ff;">Top 3 — Meilleures combinaisons (score vert)</h2>
                <ul>{top_green_html if top_green_html else "<li>Aucune combinaison optimale trouvée</li>"}</ul>
                <hr style="border-color: rgba(255,255,255,0.1);">
                <p><a href="http://{server_hostname}:4444/history.html?search_id={search_id}" style="color: #6c63ff;">Voir les résultats sur FlyCal →</a></p>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"FlyCal [{scan_type_label}] — {search.origin_city} → {search.destination_city} ({len(flights)} vols)"
        msg["From"] = user
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_email], msg.as_string())

        logger.info(f"Crawl recap email sent to {to_email}")
        _db = SessionLocal()
        try:
            log_activity(_db, "email", "sent", f"Recap for {search.origin_city}→{search.destination_city}")
        finally:
            _db.close()

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        _db = SessionLocal()
        try:
            log_activity(_db, "email", "error", f"Recap failed: {str(e)[:200]}")
        finally:
            _db.close()
    finally:
        db.close()


def send_alert_email(pin, airline, alerts_triggered, current_price, previous_price, settings=None):
    """Send a price alert email for a tracked flight."""
    if settings is None:
        settings = _get_settings()

    if settings.get("smtp_send_enabled") != "true":
        return

    host = settings.get("smtp_host", "")
    port = int(settings.get("smtp_port", "587"))
    user = settings.get("smtp_user", "")
    password = settings.get("smtp_password", "")
    to_email = settings.get("smtp_to", "")

    if not host or not user or not to_email:
        return

    server_hostname = _get_server_hostname(settings)
    airline_name = airline.name if airline else "Unknown"
    origin = pin.origin_airport
    dest = pin.destination_airport
    flight_date = pin.flight_date.isoformat() if pin.flight_date else "?"
    departure = pin.departure_time or "?"
    direction_label = "Aller" if pin.direction == "outbound" else "Retour"

    # Price change info
    price_change_html = ""
    if previous_price is not None and previous_price != current_price:
        diff = current_price - previous_price
        arrow = "↓" if diff < 0 else "↑"
        color = "#00c864" if diff < 0 else "#dc3232"
        pct = abs(diff / previous_price * 100) if previous_price else 0
        price_change_html = f'<span style="color:{color};font-weight:700">{arrow} {abs(round(diff))}€ ({pct:.0f}%)</span>'

    # Triggered conditions
    conditions_html = ""
    for a in alerts_triggered:
        if a.alert_type == "threshold":
            op = "<" if a.operator == "lt" else ">"
            unit = "%" if a.value_is_percent else "€"
            conditions_html += f"<li>Prix {op} {a.value}{unit}</li>"
        elif a.alert_type == "variation":
            conditions_html += f"<li>Variation > {a.value}%</li>"
        elif a.alert_type == "trend_start":
            d = "baisse" if a.operator == "decrease" else "hausse"
            conditions_html += f"<li>Tendance en {d}</li>"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #1a1a2e; color: #e8e8f0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: rgba(255,255,255,0.05); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.1);">
            <h1 style="color: #6c63ff;">🔔 FlyCal — Alerte Prix</h1>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 16px 0;">

            <div style="background: rgba(108,99,255,0.08); border-radius: 10px; padding: 16px; margin-bottom: 16px;">
                <p style="margin:0 0 8px 0"><strong>Compagnie:</strong> {airline_name}</p>
                <p style="margin:0 0 8px 0"><strong>Vol:</strong> {direction_label} — {origin} → {dest}</p>
                <p style="margin:0 0 8px 0"><strong>Date:</strong> {flight_date}</p>
                <p style="margin:0 0 8px 0"><strong>Départ:</strong> {departure}</p>
            </div>

            <div style="background: rgba(0,200,100,0.08); border-radius: 10px; padding: 16px; margin-bottom: 16px; text-align: center;">
                <p style="font-size: 2rem; font-weight: 700; margin: 0; color: #e8e8f0;">{round(current_price)}€</p>
                <p style="margin: 4px 0 0 0;">{price_change_html}</p>
            </div>

            <h2 style="color: #6c63ff; font-size: 1rem;">Conditions déclenchées</h2>
            <ul style="padding-left: 20px;">
                {conditions_html}
            </ul>

            <hr style="border-color: rgba(255,255,255,0.1);">
            <p><a href="http://{server_hostname}:4444/track.html" style="color: #6c63ff;">Voir mes vols suivis →</a></p>
        </div>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"FlyCal Alert — {airline_name} {origin}→{dest} {flight_date}"
        msg["From"] = user
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_email], msg.as_string())

        logger.info(f"Alert email sent for {airline_name} {origin}→{dest} {flight_date}")
        _db = SessionLocal()
        try:
            log_activity(_db, "email", "sent", f"Alert: {airline_name} {origin}→{dest}")
        finally:
            _db.close()
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        _db = SessionLocal()
        try:
            log_activity(_db, "email", "error", f"Alert email failed: {str(e)[:200]}")
        finally:
            _db.close()
