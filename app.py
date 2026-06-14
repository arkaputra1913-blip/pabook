from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
import qrcode, uuid, io, base64, csv
from datetime import datetime
import pytz
from io import StringIO
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = 'pabook-ultra-secret-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pabook.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
db = SQLAlchemy(app)

WIB = pytz.timezone('Asia/Jakarta')

def now_wib():
    return datetime.now(WIB).replace(tzinfo=None)

# Perintah gate yang menunggu diambil ESP32 (in-memory)
gate_commands = {}

# ─────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────

class ParkingSlot(db.Model):
    __tablename__ = 'parking_slots'
    id        = db.Column(db.Integer, primary_key=True)
    slot_code = db.Column(db.String(10), unique=True, nullable=False)
    zone      = db.Column(db.String(5),  nullable=False)
    status    = db.Column(db.String(20), default='available')  # available | reserved | occupied

class Reservation(db.Model):
    __tablename__ = 'reservations'
    id               = db.Column(db.Integer, primary_key=True)
    reservation_code = db.Column(db.String(50),  unique=True, nullable=False)
    vehicle          = db.Column(db.String(100), nullable=False)
    contact          = db.Column(db.String(50),  nullable=False)
    slot_code        = db.Column(db.String(10),  nullable=False)
    qr_token         = db.Column(db.String(100), unique=True, nullable=False)
    payment_method   = db.Column(db.String(50),  default='QRIS')
    price            = db.Column(db.Integer,     default=5000)
    status           = db.Column(db.String(20),  default='active')  # active | checked_in | checked_out
    created_at       = db.Column(db.DateTime,    default=now_wib)
    checked_in_at    = db.Column(db.DateTime,    nullable=True)
    checked_out_at   = db.Column(db.DateTime,    nullable=True)

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def generate_qr_base64(data: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E1155", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def init_slots():
    if ParkingSlot.query.count() == 0:
        for zone in ['A', 'B', 'C', 'D']:
            for i in range(1, 5):
                db.session.add(ParkingSlot(slot_code=f"{zone}{i}", zone=zone, status='available'))
        db.session.commit()
        print("16 slot parkir berhasil dibuat.")

# ─────────────────────────────────────────
#  CONTEXT PROCESSOR
# ─────────────────────────────────────────

@app.context_processor
def inject_defaults():
    return dict(is_admin=False)

# ─────────────────────────────────────────
#  USER ROUTES
# ─────────────────────────────────────────

@app.route('/')
def beranda():
    available = ParkingSlot.query.filter_by(status='available').count()
    total     = ParkingSlot.query.count()
    occupied  = ParkingSlot.query.filter_by(status='occupied').count()
    return render_template('beranda.html', available=available, total=total, occupied=occupied)

@app.route('/reservasi')
def reservasi():
    slots = ParkingSlot.query.order_by(ParkingSlot.zone, ParkingSlot.slot_code).all()
    return render_template('reservasi.html', slots=slots)

@app.route('/api/slots')
def api_slots():
    slots = ParkingSlot.query.all()
    return jsonify([{'slot_code': s.slot_code, 'zone': s.zone, 'status': s.status} for s in slots])

@app.route('/reservasi/proses', methods=['POST'])
def proses_reservasi():
    slot_code = request.form.get('slot_code', '').strip()
    vehicle   = request.form.get('vehicle',   '').strip()
    contact   = request.form.get('contact',   '').strip()
    payment   = request.form.get('payment_method', 'QRIS').strip()

    if not all([slot_code, vehicle, contact]):
        return redirect(url_for('reservasi'))

    slot = ParkingSlot.query.filter_by(slot_code=slot_code).first()
    if not slot or slot.status != 'available':
        return redirect(url_for('reservasi'))

    qr_token = str(uuid.uuid4())
    today    = now_wib().strftime('%Y%m%d')
    short_id = qr_token.replace('-', '')[:6].upper()
    res_code = f"PB-{today}-{short_id}"

    reservation = Reservation(
        reservation_code=res_code,
        vehicle=vehicle, contact=contact,
        slot_code=slot_code, qr_token=qr_token,
        payment_method=payment, price=5000,
        created_at=now_wib()
    )
    slot.status = 'reserved'

    db.session.add(reservation)
    db.session.commit()

    session['reservation_id'] = reservation.id
    return redirect(url_for('mytiket'))

@app.route('/mytiket')
def mytiket():
    reservation = None
    qr_image    = None
    if 'reservation_id' in session:
        reservation = Reservation.query.get(session['reservation_id'])
        if reservation:
            qr_image = generate_qr_base64(reservation.qr_token)
    return render_template('mytiket.html', reservation=reservation, qr_image=qr_image)

# ─────────────────────────────────────────
#  GATE ROUTES
# ─────────────────────────────────────────

@app.route('/gate')
def gate():
    gate_ids = {
        'entry': 'GATE-MASUK-A',
        'exit':  'GATE-KELUAR-A'
    }
    return render_template('gate.html', is_admin=True, gate_ids=gate_ids)

@app.route('/api/ping')
def api_ping():
    total     = ParkingSlot.query.count()
    available = ParkingSlot.query.filter_by(status='available').count()
    return jsonify({
        'status':           'ok',
        'server':           'Pabook Flask',
        'total_slots':      total,
        'available_slots':  available,
        'timestamp':        now_wib().strftime('%Y-%m-%d %H:%M:%S WIB')
    })

# ─────────────────────────────────────────
#  SCAN QR — AUTO DETECT (dari browser / USB scanner di halaman gate)
# ─────────────────────────────────────────

@app.route('/gate/scan/auto', methods=['POST'])
def gate_scan_auto():
    """
    Dipakai oleh browser (halaman gate scanner).
    Server otomatis menentukan gate_type berdasarkan status reservasi,
    sehingga browser tidak perlu menebak entry atau exit.
    """
    data     = request.get_json(force=True, silent=True) or {}
    qr_token = data.get('qr_token', '').strip()

    if not qr_token:
        return jsonify({'success': False, 'message': 'Token QR tidak boleh kosong!'})

    r = Reservation.query.filter_by(qr_token=qr_token).first()
    if not r:
        return jsonify({'success': False, 'message': 'QR Code tidak valid atau tidak ditemukan!'})

    slot = ParkingSlot.query.filter_by(slot_code=r.slot_code).first()

    # Auto-detect: status active/reserved → entry, checked_in → exit
    if r.status in ('active', 'reserved'):
        gate_type = 'entry'
        gate_id   = 'GATE-MASUK-A'
    elif r.status == 'checked_in':
        gate_type = 'exit'
        gate_id   = 'GATE-KELUAR-A'
    else:
        return jsonify({'success': False, 'message': 'Tiket sudah tidak aktif (kendaraan sudah keluar)!'})

    if gate_type == 'entry':
        r.status        = 'checked_in'
        r.checked_in_at = now_wib()
        if slot:
            slot.status = 'occupied'
        db.session.commit()

        gate_commands[gate_id] = {
            'command': 'open',
            'gate':    'masuk',
            'slot':    r.slot_code,
            'vehicle': r.vehicle,
            'time':    r.checked_in_at.strftime('%H:%M:%S')
        }
        return jsonify({
            'success':   True,
            'gate_type': 'entry',
            'message':   f'Selamat datang! Slot {r.slot_code} aktif untuk {r.vehicle}.',
            'slot':      r.slot_code,
            'vehicle':   r.vehicle,
        })

    else:  # exit
        r.status         = 'checked_out'
        r.checked_out_at = now_wib()
        if slot:
            slot.status = 'available'
        db.session.commit()

        delta   = r.checked_out_at - r.checked_in_at
        total_m = int(delta.total_seconds() / 60)
        h, m    = divmod(total_m, 60)

        gate_commands[gate_id] = {
            'command': 'open',
            'gate':    'keluar',
            'slot':    r.slot_code,
            'vehicle': r.vehicle,
            'time':    r.checked_out_at.strftime('%H:%M:%S')
        }
        return jsonify({
            'success':   True,
            'gate_type': 'exit',
            'message':   f'Sampai jumpa! {r.vehicle} keluar. Durasi: {h}j {m}m.',
            'slot':      r.slot_code,
            'vehicle':   r.vehicle,
            'duration':  f'{h}j {m}m',
        })

# ─────────────────────────────────────────
#  SCAN QR — MANUAL GATE TYPE (dari ESP32 langsung)
# ─────────────────────────────────────────

@app.route('/gate/scan', methods=['POST'])
def gate_scan():
    """
    Dipakai oleh ESP32 yang sudah tahu gate_type-nya (entry/exit)
    berdasarkan gate mana yang menerima scan fisik.
    """
    data      = request.get_json(force=True, silent=True) or request.form
    qr_token  = data.get('qr_token',  '').strip()
    gate_type = data.get('gate_type', 'entry')
    gate_id   = data.get('gate_id',   'UNKNOWN')

    if not qr_token:
        return jsonify({'success': False, 'message': 'Token QR tidak boleh kosong!'})

    r = Reservation.query.filter_by(qr_token=qr_token).first()
    if not r:
        return jsonify({'success': False, 'message': 'QR Code tidak valid atau tidak ditemukan!'})

    slot = ParkingSlot.query.filter_by(slot_code=r.slot_code).first()

    if gate_type == 'entry':
        if r.status == 'checked_in':
            return jsonify({'success': False, 'message': 'Kendaraan sudah tercatat masuk!'})
        if r.status == 'checked_out':
            return jsonify({'success': False, 'message': 'Tiket sudah tidak aktif!'})

        r.status        = 'checked_in'
        r.checked_in_at = now_wib()
        if slot:
            slot.status = 'occupied'
        db.session.commit()

        gate_commands[gate_id] = {
            'command': 'open', 'gate': 'masuk',
            'slot': r.slot_code, 'vehicle': r.vehicle,
            'time': r.checked_in_at.strftime('%H:%M:%S')
        }

        return jsonify({
            'success': True,
            'message': f'Selamat datang! Slot {r.slot_code} aktif untuk {r.vehicle}.',
            'slot':    r.slot_code,
            'vehicle': r.vehicle,
            'time':    r.checked_in_at.strftime('%H:%M:%S'),
            'gate_id': gate_id
        })

    elif gate_type == 'exit':
        if r.status != 'checked_in':
            return jsonify({'success': False, 'message': 'Kendaraan belum masuk atau sudah keluar!'})

        r.status         = 'checked_out'
        r.checked_out_at = now_wib()
        if slot:
            slot.status = 'available'
        db.session.commit()

        delta   = r.checked_out_at - r.checked_in_at
        total_m = int(delta.total_seconds() / 60)
        h, m    = divmod(total_m, 60)

        gate_commands[gate_id] = {
            'command': 'open', 'gate': 'keluar',
            'slot': r.slot_code, 'vehicle': r.vehicle,
            'time': r.checked_out_at.strftime('%H:%M:%S')
        }

        return jsonify({
            'success':          True,
            'message':          f'Sampai jumpa! {r.vehicle} keluar. Durasi: {h}j {m}m.',
            'slot':             r.slot_code,
            'vehicle':          r.vehicle,
            'duration':         f'{h}j {m}m',
            'duration_minutes': total_m,
            'time':             r.checked_out_at.strftime('%H:%M:%S'),
            'gate_id':          gate_id
        })

    return jsonify({'success': False, 'message': 'Tipe gate tidak dikenal!'})

# ─────────────────────────────────────────
#  KONTROL GATE MANUAL (dari Admin Web)
# ─────────────────────────────────────────

@app.route('/api/gate/open', methods=['POST'])
def gate_open_manual():
    data    = request.get_json(force=True, silent=True) or {}
    gate_id = data.get('gate_id', 'ESP32-GATE')
    gate    = data.get('gate',    'masuk')

    gate_commands[gate_id] = {
        'command': 'open',
        'gate':    gate,
        'slot':    'MANUAL',
        'vehicle': 'Override Admin',
        'time':    now_wib().strftime('%H:%M:%S')
    }
    return jsonify({'ok': True, 'gate': gate, 'gate_id': gate_id})

@app.route('/api/gate/close', methods=['POST'])
def gate_close_manual():
    data    = request.get_json(force=True, silent=True) or {}
    gate_id = data.get('gate_id', 'ESP32-GATE')
    gate    = data.get('gate',    'masuk')

    gate_commands[gate_id] = {
        'command': 'close',
        'gate':    gate,
        'slot':    '',
        'vehicle': '',
        'time':    now_wib().strftime('%H:%M:%S')
    }
    return jsonify({'ok': True, 'gate': gate, 'gate_id': gate_id})

# ─────────────────────────────────────────
#  POLLING ENDPOINT untuk ESP32
# ─────────────────────────────────────────

@app.route('/api/gate/poll', methods=['GET'])
def gate_poll():
    gate_id = request.args.get('gate_id', 'ESP32-GATE')
    cmd     = gate_commands.pop(gate_id, None)
    if cmd:
        return jsonify({'has_command': True, **cmd})
    return jsonify({'has_command': False})

# ─────────────────────────────────────────
#  STATUS GATE
# ─────────────────────────────────────────

gate_status = {}

@app.route('/api/gate/status', methods=['POST'])
def gate_status_update():
    data    = request.get_json(force=True, silent=True) or {}
    gate_id = data.get('gate_id', '')
    if gate_id:
        gate_status[gate_id] = {
            'state':     data.get('state', 'unknown'),
            'type':      data.get('type',  'unknown'),
            'timestamp': now_wib().strftime('%H:%M:%S')
        }
    return jsonify({'ok': True})

@app.route('/api/gate/status', methods=['GET'])
def gate_status_get():
    return jsonify(gate_status)

# ─────────────────────────────────────────
#  ADMIN ROUTES
# ─────────────────────────────────────────

@app.route('/admin')
def admin_dashboard():
    slots     = ParkingSlot.query.order_by(ParkingSlot.zone, ParkingSlot.slot_code).all()
    total     = len(slots)
    available = sum(1 for s in slots if s.status == 'available')
    occupied  = sum(1 for s in slots if s.status == 'occupied')
    reserved  = sum(1 for s in slots if s.status == 'reserved')

    search = request.args.get('search', '')
    q      = Reservation.query.order_by(Reservation.created_at.desc())
    if search:
        q = q.filter(db.or_(
            Reservation.vehicle.ilike(f'%{search}%'),
            Reservation.contact.ilike(f'%{search}%'),
            Reservation.slot_code.ilike(f'%{search}%'),
            Reservation.reservation_code.ilike(f'%{search}%')
        ))
    activities = q.limit(100).all()

    return render_template('admin_dashboard.html',
        slots=slots, total=total, available=available,
        occupied=occupied, reserved=reserved,
        activities=activities, search=search, is_admin=True
    )

@app.route('/admin/reset-slot/<slot_code>', methods=['POST'])
def admin_reset_slot(slot_code):
    slot = ParkingSlot.query.filter_by(slot_code=slot_code).first()
    if slot:
        slot.status = 'available'
        active_res = Reservation.query.filter_by(slot_code=slot_code).filter(
            Reservation.status.in_(['active', 'reserved', 'checked_in'])
        ).all()
        for res in active_res:
            res.status = 'checked_out'
            if not res.checked_out_at:
                res.checked_out_at = now_wib()
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export-csv')
def admin_export_csv():
    activities = Reservation.query.order_by(Reservation.created_at.desc()).all()
    si = StringIO()
    w  = csv.writer(si)
    w.writerow(['Kode','Kendaraan','Kontak','Slot','Pembayaran','Status',
                'Dibuat','Masuk','Keluar'])
    for r in activities:
        w.writerow([
            r.reservation_code, r.vehicle, r.contact, r.slot_code,
            r.payment_method, r.status,
            r.created_at.strftime('%Y-%m-%d %H:%M')    if r.created_at    else '',
            r.checked_in_at.strftime('%Y-%m-%d %H:%M') if r.checked_in_at else '',
            r.checked_out_at.strftime('%Y-%m-%d %H:%M')if r.checked_out_at else '',
        ])
    return Response(
        si.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition':
            f'attachment;filename=laporan_pabook_{now_wib().strftime("%Y%m%d_%H%M%S")}.csv'}
    )

# ─────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_slots()

    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)