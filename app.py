from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import os
import io
import re
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS FLEXIBLE
# ==========================================
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///project_data.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'una_clave_secreta_muy_segura_y_dificil_de_adivinar' 

# 1. INICIALIZAMOS LA BASE DE DATOS
db = SQLAlchemy(app)

# ==========================================
# 2. MODELOS DE LA BASE DE DATOS (Se definen ANTES del app_context)
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
    codigo_assigned = db.Column(db.String(20), unique=True, nullable=False)
    estado = db.Column(db.String(20), default="Activo")   

class Mantenimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    laboratorio = db.Column(db.String(100), nullable=False)
    tipo_tarea = db.Column(db.String(150), nullable=False)
    frecuencia = db.Column(db.String(50), nullable=False)  
    ultima_fecha = db.Column(db.Date, nullable=False)      
    proxima_fecha = db.Column(db.Date, nullable=False)     

# ==========================================
# 3. CREACIÓN AUTOMÁTICA DE TABLAS Y DATOS INICIALES
# ==========================================
with app.app_context():
    # Ahora que los modelos ya se cargaron en memoria, SQLAlchemy sí creará las tablas en Postgres
    db.create_all()  
    
    # Verificar y crear administrador por defecto si no existe
    admin_existente = Usuario.query.filter_by(username="admin").first()
    if not admin_existente:
        admin_por_defecto = Usuario(
            username="admin", password="admin", nombre="Yorman",
            apellido="Blanco", cedula="V-30397167", codigo_assigned="ADM-911", estado="Activo"
        )
        db.session.add(admin_por_defecto)
        db.session.commit()
        
    # Verificar y crear tareas de soporte iniciales si la tabla está vacía
    if Mantenimiento.query.count() == 0:
        t1 = Mantenimiento(laboratorio="Laboratorio 1", tipo_tarea="Soplado de Polvo y Pasta Térmica", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=35), proxima_fecha=date.today()-timedelta(days=5)) 
        t2 = Mantenimiento(laboratorio="Laboratorio 2", tipo_tarea="Actualización de Antivirus Nod32", frecuencia="Mensual", ultima_fecha=date.today()-timedelta(days=25), proxima_fecha=date.today()+timedelta(days=5))  
        t3 = Mantenimiento(laboratorio="Laboratorio 3", tipo_tarea="Auditoría y Clonado de Sistemas Operativos", frecuencia="Trimestral", ultima_fecha=date.today(), proxima_fecha=date.today()+timedelta(days=90)) 
        db.session.add_all([t1, t2, t3])
        db.session.commit()

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
        cedula_raw = request.form.get('cedula', '').strip()
        codigo_assigned = request.form.get('codigo')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # ==========================================
        # NUEVAS RESTRICCIONES DE SEGURIDAD
        # ==========================================
        
        # 1. Validación del campo de Usuario (Debe contener al menos una Mayúscula y una Minúscula)
        if not (any(c.isupper() for c in username) and any(c.islower() for c in username)):
            flash("El nombre de usuario debe contener obligatoriamente letras mayúsculas y minúsculas.", "error")
            return render_template('registro.html')

        # 2. Validación de la Contraseña
        # - Mayor a 12 caracteres: len(password) > 12
        # - Al menos una mayúscula: (?=.*[A-Z])
        # - Al menos una minúscula: (?=.*[a-z])
        # - Al menos un número: (?=.*\d)
        # - Al menos un carácter especial: (?=.*[!@#$%^&*(),.?":{}|<>_+\-*/\[\]])
        patron_password = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>_+\-*/\[\]]).{13,}$'
        
        if not re.match(patron_password, password):
            flash("La contraseña es insegura. Debe ser mayor a 12 dígitos y contener: letras mayúsculas, minúsculas, números y al menos un carácter especial.", "error")
            return render_template('registro.html')

        # ==========================================
        # VALIDACIONES DE DUPLICADOS EN BASE DE DATOS
        # ==========================================
        cedula_limpia = cedula_raw.replace('V-', '').replace('v-', '').strip()
        cedula_final = f"V-{cedula_limpia}"

        usuario_repetido = Usuario.query.filter_by(username=username).first()
        cedula_repetida = Usuario.query.filter_by(cedula=cedula_final).first()
        codigo_repetido = Usuario.query.filter_by(codigo_assigned=codigo_assigned).first()

        if usuario_repetido:
            flash("El nombre de usuario ya está en uso. Elige otro.", "error")
            return render_template('registro.html')
        
        if cedula_repetida:
            flash("Esta cédula ya se encuentra registrada en el sistema.", "error")
            return render_template('registro.html')

        if codigo_repetido:
            flash("Este código de asignación ya está registrado por otro usuario.", "error")
            return render_template('registro.html')

        # Si todo está perfecto, se procede a crear el usuario
        nuevo_usuario = Usuario(
            username=username,
            password=password,
            nombre=nombre,
            apellido=apellido,
            cedula=cedula_final, 
            codigo_assigned=codigo_assigned,
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
    
    hoy = date.today()
    
    if frecuencia_form == "Mensual":
        proxima = hoy + timedelta(days=30)
    elif frecuencia_form == "Trimestral":
        proxima = hoy + timedelta(days=90)
    elif frecuencia_form == "Semestral":
        proxima = hoy + timedelta(days=180)
    else:
        proxima = hoy + timedelta(days=365)
        
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

@app.route('/acceso/eliminar/<int:usuario_id>', methods=['POST'])
def eliminar_usuario(usuario_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if session['usuario'] != 'admin':
        flash("Acceso denegado: Operación no permitida.", "error")
        return redirect(url_for('home'))
    
    usuario_a_eliminar = Usuario.query.get_or_404(usuario_id)
    
    # Seguridad básica: que el admin no se borre a sí mismo
    if usuario_a_eliminar.username == session['usuario']:
        flash("No puedes eliminar tu propia cuenta de administrador.", "error")
        return redirect(url_for('acceso'))
    
    db.session.delete(usuario_a_eliminar)
    db.session.commit()
    flash(f"El usuario '{usuario_a_eliminar.username}' ha sido eliminado del sistema permanentemente.", "success")
    return redirect(url_for('acceso'))


@app.route('/acceso/editar/<int:usuario_id>', methods=['POST'])
def editar_usuario(usuario_id):
    if 'usuario' not in session:
        return redirect(url_for('login'))
        
    if session['usuario'] != 'admin':
        flash("Acceso denegado: Operación no permitida.", "error")
        return redirect(url_for('home'))
    
    usuario_a_editar = Usuario.query.get_or_404(usuario_id)
    
    nuevo_username = request.form.get('username', '').strip()
    nueva_password = request.form.get('password', '')

    if not nuevo_username or not nueva_password:
        flash("El usuario y la contraseña no pueden estar vacíos.", "error")
        return redirect(url_for('acceso'))

    # Validar que si cambia el username, no se mueva a uno que ya exista (duplicado)
    if nuevo_username != usuario_a_editar.username:
        existente = Usuario.query.filter_by(username=nuevo_username).first()
        if existente:
            flash("Ese nombre de usuario ya está ocupado por otra persona.", "error")
            return redirect(url_for('acceso'))

    # Aplicamos los cambios que el administrador digitó
    usuario_a_editar.username = nuevo_username
    usuario_a_editar.password = nueva_password
    
    db.session.commit()
    flash(f"Credenciales actualizadas con éxito para el usuario ID #{usuario_id}.", "success")
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
# RUTAS DE EXPORTACIÓN ULTRA-SEGURAS
# ==========================================

@app.route('/exportar/excel')
def exportar_excel():
    todos_los_equipos = Equipo.query.all()
        
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventario de Laboratorio"
    ws.views.sheetView[0].showGridLines = True
    
    font_titulo = Font(name="Arial", size=16, bold=True, color="1F497D")
    font_cabecera = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    font_datos = Font(name="Arial", size=10)
    
    fill_cabecera = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    fill_cebra = PatternFill(start_color="F2F5F8", end_color="F2F5F8", fill_type="solid")
    
    align_centro = Alignment(horizontal="center", vertical="center")
    align_izquierda = Alignment(horizontal="left", vertical="center")
    
    borde_delgado = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )
    
    ws['A1'] = "REPORTE GENERAL DE INVENTARIO - LAB-INVENTORY"
    ws['A1'].font = font_titulo
    ws.row_dimensions[1].height = 30
    ws.append([])
    
    cabeceras = ["ID Equipo", "Nombre / Modelo", "Laboratorio", "Estado"]
    ws.append(cabeceras)
    
    ws.row_dimensions[3].height = 24
    for col_num, cabecera in enumerate(cabeceras, 1):
        cell = ws.cell(row=3, column=col_num)
        cell.font = font_cabecera
        cell.fill = fill_cabecera
        cell.alignment = align_centro
        cell.border = borde_delgado
        
    fila_actual = 4
    
    if not todos_los_equipos:
        ws.append(["No hay equipos registrados en el sistema", "", "", ""])
        ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=4)
        cell = ws.cell(row=fila_actual, column=1)
        cell.font = font_datos
        cell.alignment = align_centro
    else:
        for idx, equipo in enumerate(todos_los_equipos):
            id_safe = f"#PC-0{equipo.id}" if equipo.id else "#PC-00"
            nombre_safe = str(equipo.nombre) if equipo.nombre else "S/N"
            lab_safe = str(equipo.laboratorio) if equipo.laboratorio else "Sin Asignar"
            estado_safe = str(equipo.estado) if equipo.estado else "Disponible"
            
            datos_fila = [id_safe, nombre_safe, lab_safe, estado_safe]
            ws.append(datos_fila)
            
            ws.row_dimensions[fila_actual].height = 20
            for col_num in range(1, len(datos_fila) + 1):
                cell = ws.cell(row=fila_actual, column=col_num)
                cell.font = font_datos
                cell.border = borde_delgado
                if col_num in [1, 4]:
                    cell.alignment = align_centro
                else:
                    cell.alignment = align_izquierda
                if idx % 2 != 0:
                    cell.fill = fill_cebra
            fila_actual += 1
        
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.row == 1: continue
            if cell.value: max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='reporte_inventario.xlsx'
    )

@app.route('/exportar/pdf')
def exportar_pdf():
    todos_los_equipos = Equipo.query.all()

    pdf_out = io.BytesIO()
    
    doc = SimpleDocTemplate(
        pdf_out, pagesize=A4,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    style_titulo = ParagraphStyle(
        'TituloReporte', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor('#1F497D'), spaceAfter=6
    )
    style_subtitulo = ParagraphStyle(
        'SubtituloReporte', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=10, textColor=colors.HexColor('#555555'), spaceAfter=20
    )
    style_celda_cabecera = ParagraphStyle(
        'CeldaCabecera', fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, alignment=1
    )
    style_celda_datos = ParagraphStyle(
        'CeldaDatos', fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#333333')
    )
    
    story.append(Paragraph("LAB-INVENTORY MANAGER", style_titulo))
    story.append(Paragraph("Reporte Oficial de Existencias e Insumos de Laboratorio", style_subtitulo))
    story.append(Spacer(1, 10))
    
    tabla_datos = [[
        Paragraph("ID Equipo", style_celda_cabecera),
        Paragraph("Nombre / Modelo", style_celda_cabecera),
        Paragraph("Laboratorio", style_celda_cabecera),
        Paragraph("Estado", style_celda_cabecera)
    ]]
    
    if not todos_los_equipos:
        tabla_datos.append([
            Paragraph("No hay equipos registrados en el sistema actualmente.", style_celda_datos),
            Paragraph("", style_celda_datos),
            Paragraph("", style_celda_datos),
            Paragraph("", style_celda_datos)
        ])
    else:
        for equipo in todos_los_equipos:
            id_safe = f"#PC-0{equipo.id}" if equipo.id else "#PC-00"
            nombre_safe = str(equipo.nombre) if equipo.nombre else "S/N"
            lab_safe = str(equipo.laboratorio) if equipo.laboratorio else "Sin Asignar"
            estado_safe = str(equipo.estado) if equipo.estado else "Disponible"
            
            tabla_datos.append([
                Paragraph(id_safe, style_celda_datos),
                Paragraph(nombre_safe, style_celda_datos),
                Paragraph(lab_safe, style_celda_datos),
                Paragraph(estado_safe, style_celda_datos)
            ])
        
    anchos_columnas = [65, 180, 150, 120]
    tabla_pdf = Table(tabla_datos, colWidths=anchos_columnas, repeatRows=1)
    
    estilo_tabla = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F497D')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D9D9D9')),
    ])
    
    if not todos_los_equipos:
        estilo_tabla.add('SPAN', (0, 1), (-1, 1))
        estilo_tabla.add('ALIGN', (0, 1), (-1, 1), 'CENTER')
    else:
        for i in range(1, len(tabla_datos)):
            if i % 2 == 0:
                estilo_tabla.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F2F5F8'))
            
    tabla_pdf.setStyle(estilo_tabla)
    story.append(tabla_pdf)
    
    doc.build(story)
    pdf_out.seek(0)
    
    return send_file(
        pdf_out,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='reporte_inventario.pdf'
    )

# ==========================================
# BLOQUE DE ARRANQUE PARA EJECUCIÓN LOCAL
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)