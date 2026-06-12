from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import os
import io
import re
import openpyxl

app = Flask(__name__)

# CONFIGURACIÓN
app.secret_key = os.environ.get('SECRET_KEY', 'una_clave_muy_segura_y_larga')
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///project_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELOS
class Equipo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    laboratorio = db.Column(db.String(100), nullable=False)
    componentes = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default="Disponible")

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    codigo_assigned = db.Column(db.String(20), unique=True, nullable=False)
    estado = db.Column(db.String(20), default="Activo")
    es_temporal = db.Column(db.Boolean, default=False)

class Mantenimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    laboratorio = db.Column(db.String(100), nullable=False)
    tipo_tarea = db.Column(db.String(150), nullable=False)
    frecuencia = db.Column(db.String(50), nullable=False)
    ultima_fecha = db.Column(db.Date, nullable=False)
    proxima_fecha = db.Column(db.Date, nullable=False)

with app.app_context():
    db.create_all()
    # Crear admin por defecto si no existe
    if not Usuario.query.filter_by(username="admin").first():
        admin_por_defecto = Usuario(
            username="admin", password="admin", nombre="Yorman",
            apellido="Blanco", cedula="V-30397167", codigo_assigned="ADM-911", estado="Activo"
        )
        db.session.add(admin_por_defecto)
        db.session.commit()
        
    # Tareas de mantenimiento de prueba
    if Mantenimiento.query.count() == 0:
        t1 = Mantenimiento(laboratorio="Laboratorio 1", tipo_tarea="Soplado de Polvo y Pasta Térmica", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=35), proxima_fecha=date.today()-timedelta(days=5)) 
        t2 = Mantenimiento(laboratorio="Laboratorio 2", tipo_tarea="Actualización de Antivirus Nod32", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=25), proxima_fecha=date.today()+timedelta(days=5))  
        t3 = Mantenimiento(laboratorio="Laboratorio 3", tipo_tarea="Auditoría y Clonado de Sistemas Operativos", frecuencia="Trimestral", ultima_fecha=date.today(), proxima_fecha=date.today()+timedelta(days=90)) 
        db.session.add_all([t1, t2, t3])
        db.session.commit()

# ==========================================
# RUTAS PRINCIPALES Y AUTENTICACIÓN
# ==========================================
@app.route('/')
def home():
    if 'usuario' in session:
        return render_template('dashboard.html', usuario_actual=session['usuario'])
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form['usuario'], password=request.form['contrasena']).first()
        if user and user.estado == "Activo":
            session['usuario'] = user.username
            if user.es_temporal:
                flash("Debes cambiar tu contraseña temporal.", "warning")
                return redirect(url_for('cambiar_clave'))
            return redirect(url_for('home'))
        flash('Credenciales incorrectas o usuario inactivo', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cambiar_clave', methods=['GET', 'POST'])
def cambiar_clave():
    if 'usuario' not in session: return redirect(url_for('login'))
    usuario = Usuario.query.filter_by(username=session['usuario']).first()
    if request.method == 'POST':
        usuario.password = request.form.get('password')
        usuario.es_temporal = False
        db.session.commit()
        flash("Contraseña actualizada.", "success")
        return redirect(url_for('home'))
    return render_template('cambiar_clave.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if 'usuario' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        cedula_raw = request.form.get('cedula', '').strip()
        codigo_assigned = request.form.get('codigo')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not (any(c.isupper() for c in username) and any(c.islower() for c in username)):
            flash("El nombre de usuario debe contener obligatoriamente letras mayúsculas y minúsculas.", "error")
            return render_template('registro.html')

        patron_password = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>_+\-*/\[\]]).{13,}$'
        if not re.match(patron_password, password):
            flash("La contraseña es insegura. Debe ser mayor a 12 dígitos y contener: letras mayúsculas, minúsculas, números y al menos un carácter especial.", "error")
            return render_template('registro.html')

        cedula_limpia = cedula_raw.replace('V-', '').replace('v-', '').strip()
        cedula_final = f"V-{cedula_limpia}"

        if Usuario.query.filter_by(username=username).first():
            flash("El nombre de usuario ya está en uso. Elige otro.", "error")
            return render_template('registro.html')
        if Usuario.query.filter_by(cedula=cedula_final).first():
            flash("Esta cédula ya se encuentra registrada en el sistema.", "error")
            return render_template('registro.html')
        if Usuario.query.filter_by(codigo_assigned=codigo_assigned).first():
            flash("Este código de asignación ya está registrado por otro usuario.", "error")
            return render_template('registro.html')

        nuevo_usuario = Usuario(
            username=username, password=password, nombre=nombre, apellido=apellido,
            cedula=cedula_final, codigo_assigned=codigo_assigned, estado="Activo" 
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        session['usuario'] = nuevo_usuario.username
        flash("¡Cuenta creada con éxito! Bienvenido al sistema.", "success")
        return redirect(url_for('home'))

    return render_template('registro.html')

# ==========================================
# MÓDULO DE INVENTARIO
# ==========================================
@app.route('/inventario')
def inventario():
    if 'usuario' not in session: return redirect(url_for('login'))
    return render_template('inventario.html', usuario_actual=session['usuario'], equipos=Equipo.query.all())

@app.route('/inventario/registrar', methods=['GET', 'POST'])
def registrar_equipo():
    if 'usuario' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        nuevo_equipo = Equipo(
            nombre=request.form.get('nombre'), 
            laboratorio=request.form.get('laboratorio'), 
            componentes=request.form.get('componentes'),
            estado=request.form.get('estado') 
        )
        db.session.add(nuevo_equipo)
        db.session.commit()
        flash(f"Equipo '{nuevo_equipo.nombre}' registrado con éxito.", "success")
        return redirect(url_for('inventario'))
    return render_template('registrar_equipo.html', usuario_actual=session['usuario'])

@app.route('/equipo/completar/<int:equipo_id>', methods=['POST'])
def completar_mantenimiento(equipo_id):
    if 'usuario' not in session: return redirect(url_for('login'))
    equipo = Equipo.query.get_or_404(equipo_id)
    equipo.estado = "Disponible"
    db.session.commit()
    flash(f"El equipo '{equipo.nombre}' ahora está Operativo.", "success")
    return redirect(url_for('home'))

# ==========================================
# MÓDULO DE MANTENIMIENTO
# ==========================================
@app.route('/mantenimiento')
def mantenimiento():
    if 'usuario' not in session: return redirect(url_for('login'))
    admin_info = Usuario.query.filter_by(username=session['usuario']).first()
    tareas = Mantenimiento.query.all()
    tareas_procesadas = []
    hoy = date.today()
    
    for tarea in tareas:
        dias_restantes = (tarea.proxima_fecha - hoy).days
        color = "rojo" if dias_restantes < 0 else "amarillo" if dias_restantes <= 7 else "verde"
        estatus = "Vencido" if dias_restantes < 0 else "Próximo a vencer" if dias_restantes <= 7 else "Al día"
            
        tareas_procesadas.append({
            'id': tarea.id, 'laboratorio': tarea.laboratorio, 'tipo_tarea': tarea.tipo_tarea,
            'frecuencia': tarea.frecuencia, 'ultima_fecha': tarea.ultima_fecha.strftime('%d/%m/%Y'),
            'proxima_fecha': tarea.proxima_fecha.strftime('%d/%m/%Y'),
            'dias_restantes': dias_restantes, 'color': color, 'estatus': estatus
        })
        
    return render_template('mantenimiento.html', usuario_actual=session['usuario'], admin=admin_info, tareas=tareas_procesadas)

@app.route('/mantenimiento/crear', methods=['POST'])
def crear_mantenimiento():
    if 'usuario' not in session: return redirect(url_for('login'))
    hoy = date.today()
    frecuencia = request.form.get('frecuencia')
    dias_extra = 30 if frecuencia == "Mensual" else 90 if frecuencia == "Trimestral" else 180 if frecuencia == "Semestral" else 365
    
    nueva_tarea = Mantenimiento(
        laboratorio=request.form.get('laboratorio'),
        tipo_tarea=request.form.get('tipo_tarea'),
        frecuencia=frecuencia, ultima_fecha=hoy, proxima_fecha=hoy + timedelta(days=dias_extra)
    )
    db.session.add(nueva_tarea)
    db.session.commit()
    flash(f"¡Nueva tarea de soporte añadida con éxito para el {nueva_tarea.laboratorio}!", "success")
    return redirect(url_for('mantenimiento'))

@app.route('/mantenimiento/completar/<int:tarea_id>', methods=['POST'])
def realizar_mantenimiento(tarea_id):
    if 'usuario' not in session: return redirect(url_for('login'))
    tarea = Mantenimiento.query.get_or_404(tarea_id)
    hoy = date.today()
    tarea.ultima_fecha = hoy
    dias_extra = 30 if tarea.frecuencia == "Mensual" else 90 if tarea.frecuencia == "Trimestral" else 180 if tarea.frecuencia == "Semestral" else 365
    tarea.proxima_fecha = hoy + timedelta(days=dias_extra)
    db.session.commit()
    flash(f"¡Mantenimiento técnico registrado con éxito para el {tarea.laboratorio}!", "success")
    return redirect(url_for('mantenimiento'))

# ==========================================
# MÓDULO DE ADMINISTRACIÓN DE ACCESO
# ==========================================
@app.route('/acceso')
def acceso():
    if session.get('usuario') != 'admin': return redirect(url_for('home'))
    return render_template('acceso.html', usuarios=Usuario.query.all())

@app.route('/acceso/cambiar_estado/<int:usuario_id>', methods=['POST'])
def cambiar_estado_usuario(usuario_id):
    u = Usuario.query.get_or_404(usuario_id)
    u.estado = "Inactivo" if u.estado == "Activo" else "Activo"
    db.session.commit()
    return redirect(url_for('acceso'))

@app.route('/acceso/eliminar/<int:usuario_id>', methods=['POST'])
def eliminar_usuario(usuario_id):
    db.session.delete(Usuario.query.get_or_404(usuario_id))
    db.session.commit()
    return redirect(url_for('acceso'))

@app.route('/acceso/editar/<int:usuario_id>', methods=['POST'])
def editar_usuario(usuario_id):
    if session.get('usuario') != 'admin': return redirect(url_for('home'))
    u = Usuario.query.get_or_404(usuario_id)
    u.username = request.form.get('username')
    u.password = request.form.get('password')
    u.es_temporal = True
    db.session.commit()
    flash(f"Usuario {u.username} actualizado correctamente.", "success")
    return redirect(url_for('acceso'))

@app.route('/acceso/editar_credenciales/<int:usuario_id>', methods=['POST'])
def editar_credenciales(usuario_id):
    u = Usuario.query.get_or_404(usuario_id)
    u.username = request.form.get('username')
    u.password = request.form.get('password')
    u.es_temporal = True
    db.session.commit()
    flash(f"Credenciales de {u.nombre} actualizadas. Cambio obligatorio activado.", "success")
    return redirect(url_for('acceso'))

@app.route('/toggle_estado/<int:usuario_id>', methods=['POST'])
def toggle_estado(usuario_id):
    # Supongamos que tienes una función para obtener tu usuario
    usuario = Usuario.query.get_or_404(usuario_id)
    
    # Cambiamos el estado
    if usuario.estado == "Activo":
        usuario.estado = "Inactivo"
    else:
        usuario.estado = "Activo"
        
    db.session.commit()
    flash(f"Estado de {usuario.nombre} actualizado a {usuario.estado}", "success")
    return redirect(url_for('acceso'))

# ==========================================
# EXPORTACIÓN
# ==========================================
@app.route('/exportar/excel')
def exportar_excel():
    todos_los_equipos = Equipo.query.all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventario de Laboratorio"
    
    # Aquí puedes continuar tu lógica de Openpyxl tranquilamente
    # ...
    
    # Para retornar el archivo sin guardarlo en disco
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, download_name="Inventario.xlsx", as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)