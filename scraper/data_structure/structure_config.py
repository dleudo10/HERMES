import re

COLUMNAS = {
    "tdoc": ["TDOC", "TIPODOC", "TIPODOCUMENTO"],
    "documento": ["IDENTIFICACION", "DOCUMENTO", "NUMERODOCUMENTO"],
    "ingreso": ["INGRESO"],
    "fecha": ["FECHA_CITA", "FECHACITA"],
    "estado": ["ESTADO"],
    "especialidad": ["ESPECIALIDAD"],
    "email": ["EMAIL", "CORREO", "CORREOELECTRONICO"],
    "nombre": ["NOMPREPACIETNE", "NOMBREPACIENTE", "NOMBRE_PACIENTE", "PACIENTE"],
    "cit_folio": ["CITFOLIO", "CIT_FOLIO"],
}

REQUERIDAS = [
    "tdoc",
    "documento",
    "ingreso",
    "fecha",
    "estado",
    "especialidad",
    "cit_folio",
]

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+" r"(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$"
)

DOMINIOS_SOSPECHOSOS = {
    "gmal.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.co": "gmail.com",
    "gmai.com": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotmai.com": "hotmail.com",
    "hotmail.con": "hotmail.com",
    "outlok.com": "outlook.com",
    "outlook.con": "outlook.com",
    "yaho.com": "yahoo.com",
    "yahoo.con": "yahoo.com",
}

EXCEL_TO_MODEL = {
    "Sede_Atencion": "sede_atencion",
    "Sede_asignacion": "sede_asignacion",
    "Consul": "consul",
    "Consultorio": "consultorio",
    "CitNum": "cit_num",
    "Ingreso": "ingreso",
    "CodEspec": "cod_espec",
    "Especialidad": "especialidad",
    "CodMedico": "cod_medico",
    "NombreMedico": "nombre_medico",
    "Estado": "estado",
    "CitFolio": "cit_folio",
    "tdoc": "tdoc",
    "identificacion": "identificacion",
    "NomprePacietne": "nombre_paciente",
    "Telefono": "telefono",
    "FechaNacimiento": "fecha_nacimiento",
    "Edad": "edad",
    "FecharealSol": "fecha_real_solicitud",
    "CitHorIPa": "hora_cita",
    "Fecha_Cita": "fecha_cita",
    "IngSalDx": "ingreso_salida_dx",
    "NombreDiag": "nombre_diagnostico",
    "CodCUPS": "cod_cups",
    "prnomb": "procedimiento",
    "Contrato": "contrato",
    "NombreContrato": "nombre_contrato",
    "MPSexo": "sexo",
    "Aut": "autorizacion",
    "Autorizador": "autorizador",
    "Email": "email",
}
