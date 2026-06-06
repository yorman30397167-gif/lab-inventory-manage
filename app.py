from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta

app = Flask(__name__)

# CONFIGURACIONES DE LA APLICACIÓN
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project_data.db'
app.secret_key = 'una_clave_secreta_muy_segura_y_dificil_de_adivinar' 

# INICIALIZACIÓN DE LA BASE DE DATOS
db = SQLAlchemy(app)

# ==========================================
# MODELOS DE LA BASE DE DATOS
# ==========================================

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
    codigo_asignado = db.Column(db.String(20), unique=True, nullable=False)
    estado = db.Column(db.String(20), default="Activo")   

class Mantenimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    laboratorio = db.Column(db.String(100), nullable=False)
    tipo_tarea = db.Column(db.String(150), nullable=False) # Ej: Limpieza física, Actualizar software
    frecuencia = db.Column(db.String(50), nullable=False)   # Ej: Mensual, Trimestral
    ultima_fecha = db.Column(db.Date, nullable=False)      # Cuándo se hizo por última vez
    proxima_fecha = db.Column(db.Date, nullable=False)     # Cuándo le toca obligatoriamente

# ==========================================
# RUTAS DE LA APLICACIÓN
# ==========================================

@app.route('/')
def home():
    if 'usuario' in session:
        total = Equipo.query.count()
        operativos = Equipo.query.filter_by(estado="Disponible").count()
        en_mantenimiento = Equipo.query.filter_by(estado="En Mantenimiento").count()
        equipos_recientes = Equipo.query.all()
        
        admin_info = Usuario.query.filter_by(username=session['usuario']).first()
        
        return render_template(
            'dashboard.html', 
            usuario_actual=session['usuario'], 
            admin=admin_info,  
            total_equipos=total,
            equipos_operativos=operativos,
            mantenimiento_equipos=en_mantenimiento,
            equipos=equipos_recientes
        )
        
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        usuario_ingresado = request.form['usuario']
        clave_ingresada = request.form['contrasena']
        
        usuario_valido = Usuario.query.filter_by(username=usuario_ingresado, password=clave_ingresada).first()
        
        if usuario_valido:
            if usuario_valido.estado == "Activo":
                session['usuario'] = usuario_valido.username  
                flash('¡Inicio de sesión exitoso!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Tu usuario está Inactivo. Comunícate con soporte.', 'error')
                return render_template('login.html')
        else:
            flash('Usuario o contraseña incorrectos.', 'error')
            return render_template('login.html')
            
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if 'usuario' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        cedula = request.form.get('cedula')
        codigo = request.form.get('codigo')
        username = request.form.get('usuario')
        password = request.form.get('contrasena')

        usuario_repetido = Usuario.query.filter_by(username=username).first()
        cedula_repetida = Usuario.query.filter_by(cedula=f"V-{cedula}").first()

        if usuario_repetido:
            flash("El nombre de usuario ya está en uso. Elige otro.", "error")
            return render_template('registro.html')
        
        if cedula_repetida:
            flash("Esta cédula ya se encuentra registrada en el sistema.", "error")
            return render_template('registro.html')

        nuevo_usuario = Usuario(
            username=username,
            password=password,
            nombre=nombre,
            apellido=apellido,
            cedula=f"V-{cedula}", 
            codigo_asignado=codigo,
            estado="Activo" 
        )

        db.session.add(nuevo_usuario)
        db.session.commit()

        session['usuario'] = nuevo_usuario.username
        flash("¡Cuenta creada con éxito! Bienvenido al sistema.", "success")
        return redirect(url_for('home'))

    return render_template('registro.html')

@app.route('/inventario')
def inventario():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    lista_equipos = Equipo.query.all()
    
    return render_template(
        'inventario.html', 
        usuario_actual=session['usuario'], 
        equipos=lista_equipos
    )

@app.route('/inventario/registrar', methods=['GET', 'POST'])
def registrar_equipo():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        nombre_form = request.form.get('nombre')
        laboratorio_form = request.form.get('laboratorio')
        componentes_form = request.form.get('componentes')
        estado_form = request.form.get('estado') 
        
        nuevo_equipo = Equipo(
            nombre=nombre_form, 
            laboratorio=laboratorio_form, 
            componentes=componentes_form,
            estado=estado_form 
        )
        
        db.session.add(nuevo_equipo)
        db.session.commit()
        
        flash(f"Equipo '{nombre_form}' registrado con éxito.", "success")
        return redirect(url_for('inventario'))
        
    return render_template('registrar_equipo.html', usuario_actual=session['usuario'])

@app.route('/mantenimiento')
def mantenimiento():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    admin_info = Usuario.query.filter_by(username=session['usuario']).first()
    tareas = Mantenimiento.query.all()
    
    tareas_procesadas = []
    hoy = date.today()
    
    for tarea in tareas:
        dias_restantes = (tarea.proxima_fecha - hoy).days
        
        if dias_restantes < 0:
            color = "rojo"
            estatus = "Vencido"
        elif dias_restantes <= 7:
            color = "amarillo"
            estatus = "Próximo a vencer"
        else:
            color = "verde"
            estatus = "Al día"
            
        tareas_procesadas.append({
            'id': tarea.id,
            'laboratorio': tarea.laboratorio,
            'tipo_tarea': tarea.tipo_tarea,
            'frecuencia': tarea.frecuencia,
            'ultima_fecha': tarea.ultima_fecha.strftime('%d/%m/%Y'),
            'proxima_fecha': tarea.proxima_fecha.strftime('%d/%m/%Y'),
            'dias_restantes': dias_restantes,
            'color': color,
            'estatus': estatus
        })
        
    return render_template(
        'mantenimiento.html', 
        usuario_actual=session['usuario'], 
        admin=admin_info, 
        tareas=tareas_procesadas
    )

@app.route('/mantenimiento/crear', methods=['POST'])
def crear_mantenimiento():
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    laboratorio_form = request.form.get('laboratorio')
    tipo_tarea_form = request.form.get('tipo_tarea')
    frecuencia_form = request.form.get('frecuencia')
    
    # Automatización: Se registra que se hizo HOY por primera vez
    hoy = date.today()
    
    # Calculamos de una vez su próxima fecha de vencimiento según la frecuencia elegida
    if frecuencia_form == "Mensual":
        proxima = hoy + timedelta(days=30)
    elif frecuencia_form == "Trimestral":
        proxima = hoy + timedelta(days=90)
    elif frecuencia_form == "Semestral":
        proxima = hoy + timedelta(days=180)
    else:
        proxima = hoy + timedelta(days=365)
        
    # Guardamos en la base de datos
    nueva_tarea = Mantenimiento(
        laboratorio=laboratorio_form,
        tipo_tarea=tipo_tarea_form,
        frecuencia=frecuencia_form,
        ultima_fecha=hoy,
        proxima_fecha=proxima
    )
    
    db.session.add(nueva_tarea)
    db.session.commit()
    
    flash(f"¡Nueva tarea de soporte añadida con éxito para el {laboratorio_form}!", "success")
    return redirect(url_for('mantenimiento'))

@app.route('/mantenimiento/completar/<int:tarea_id>', methods=['POST'])
def realizar_mantenimiento(tarea_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    tarea = Mantenimiento.query.get_or_404(tarea_id)
    hoy = date.today()
    tarea.ultima_fecha = hoy
    
    if tarea.frecuencia == "Mensual":
        tarea.proxima_fecha = hoy + timedelta(days=30)
    elif tarea.frecuencia == "Trimestral":
        tarea.proxima_fecha = hoy + timedelta(days=90)
    elif tarea.frecuencia == "Semestral":
        tarea.proxima_fecha = hoy + timedelta(days=180)
    else:
        tarea.proxima_fecha = hoy + timedelta(days=365)
        
    db.session.commit()
    flash(f"¡Mantenimiento técnico registrado con éxito para el {tarea.laboratorio}!", "success")
    return redirect(url_for('mantenimiento'))

# ==========================================
# VISTAS DE ACCESO PROTEGIDAS (SOLO ADMIN)
# ==========================================

@app.route('/acceso')
def acceso():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    # CANDADO DE ROL: Si no es el admin real, lo saca al home
    if session['usuario'] != 'admin':
        flash("Acceso denegado: No tienes permisos de administrador.", "error")
        return redirect(url_for('home'))
    
    admin_info = Usuario.query.filter_by(username=session['usuario']).first()
    lista_usuarios = Usuario.query.all()
    
    return render_template(
        'acceso.html', 
        usuario_actual=session['usuario'], 
        admin=admin_info, 
        usuarios=lista_usuarios
    )

@app.route('/acceso/cambiar_estado/<int:usuario_id>', methods=['POST'])
def cambiar_estado_usuario(usuario_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    # CANDADO DE ROL: Evita peticiones maliciosas externas en esta acción
    if session['usuario'] != 'admin':
        flash("Acceso denegado: Operación no permitida.", "error")
        return redirect(url_for('home'))
    
    usuario_a_cambiar = Usuario.query.get_or_404(usuario_id)
    
    if usuario_a_cambiar.username == session['usuario']:
        flash("No puedes desactivar tu propia cuenta de administrador.", "error")
        return redirect(url_for('acceso'))
    
    if usuario_a_cambiar.estado == "Activo":
        usuario_a_cambiar.estado = "Inactivo"
    else:
        usuario_a_cambiar.estado = "Activo"
        
    db.session.commit()
    flash(f"Estado del usuario '{usuario_a_cambiar.username}' actualizado correctamente.", "success")
    return redirect(url_for('acceso'))

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

@app.route('/equipo/completar/<int:equipo_id>', methods=['POST'])
def completar_mantenimiento(equipo_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    equipo = Equipo.query.get_or_404(equipo_id)
    equipo.estado = "Disponible"
    db.session.commit()
    
    flash(f"El equipo '{equipo.nombre}' ahora está Operativo.", "success")
    return redirect(url_for('home'))


# ==========================================
# BLOQUE DE ARRANQUE ÚNICO (AL FINAL)
# ==========================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  
        
        admin_existente = Usuario.query.filter_by(username="admin").first()
        if not admin_existente:
            admin_por_defecto = Usuario(
                username="admin", password="admin", nombre="Yorman",
                apellido="Blanco", cedula="V-30397167", codigo_asignado="ADM-911", estado="Activo"
            )
            db.session.add(admin_por_defecto)
            db.session.commit()
            
        if Mantenimiento.query.count() == 0:
            t1 = Mantenimiento(laboratorio="Laboratorio 1", tipo_tarea="Soplado de Polvo y Pasta Térmica", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=35), proxima_fecha=date.today()-timedelta(days=5)) 
            t2 = Mantenimiento(laboratorio="Laboratorio 2", tipo_tarea="Actualización de Antivirus Nod32", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=25), proxima_fecha=date.today()+timedelta(days=5))  
            t3 = Mantenimiento(laboratorio="Laboratorio 3", tipo_tarea="Auditoría y Clonado de Sistemas Operativos", frecuencia="Trimestral", ultima_fecha=date.today(), proxima_fecha=date.today()+timedelta(days=90)) 
            db.session.add_all([t1, t2, t3])
            db.session.commit()


    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
   