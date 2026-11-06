from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin
from playwright.async_api import (
    Page,
    Frame,
    TimeoutError as PlaywrightTimeoutError,
)

from ..models.document import DocumentStatus, DocumentType


class PatientNotFoundError(Exception):
    """No hay resultados para el paciente o no existe el ingreso indicado."""


class DocumentNotFoundError(Exception):
    """El sistema no tiene documentos de este tipo para el paciente."""


@dataclass
class DocumentResult:
    """Resultado de intentar descargar un tipo de documento."""

    type_document: str
    status: str = DocumentStatus.FAILED
    files: list[Path] = field(default_factory=list)
    message: str | None = None


class ClinicalExtractor:

    BASE_URL = "http://10.0.0.80:8082/Hosvital/servlet"

    DEFAULT_TIMEOUT = 15000

    def __init__(self, page: Page):
        self.page = page
        self.page.set_default_timeout(self.DEFAULT_TIMEOUT)

    # --------------------------------------------------
    # MÉTODOS AUXILIARES
    # --------------------------------------------------

    def get_frame(self, name: str) -> Frame:
        """
        Obtiene un frame por su nombre.
        """
        frame = self.page.frame(name=name)

        if frame is None:
            raise Exception(f"No se encontró el frame: {name}")

        return frame

    async def wait_for_frame(self, name: str, timeout: int = 15000) -> Frame:
        """
        Espera hasta que exista un frame.
        """

        await self.page.wait_for_function(
            """(name) => {
                return Array.from(window.frames)
                    .some(frame => frame.name === name);
            }""",
            arg=name,
            timeout=timeout,
        )

        return self.get_frame(name)

    # --------------------------------------------------
    # ABRIR SISTEMA
    # --------------------------------------------------

    async def open_system(self):
        """
        Abre el sistema hospitalario.
        """

        await self.page.goto(f"{self.BASE_URL}/login", wait_until="domcontentloaded")

        await self.page.locator("#vUSUARIO1").wait_for(state="visible")

    # --------------------------------------------------
    # LOGIN
    # --------------------------------------------------

    async def login(self, username: str, password: str):
        """
        Inicio de sesión robusto.
        """

        usuario = self.page.locator("#vUSUARIO1")
        contrasena = self.page.locator("#vCONTRASENA")
        sede = self.page.locator("#vSEDENOM")

        # Esperar campos visibles
        await usuario.wait_for(state="visible")
        await contrasena.wait_for(state="visible")
        await sede.wait_for(state="visible")

        # Limpiar y diligenciar usuario
        await usuario.fill("")
        await usuario.fill(username)

        # Verificar usuario
        if await usuario.input_value() != username:
            raise ValueError("El usuario no se diligenció correctamente")

        # Limpiar y diligenciar contraseña
        await contrasena.fill("")
        await contrasena.fill(password)

        # Verificar contraseña
        if await contrasena.input_value() != password:
            raise ValueError("La contraseña no se diligenció correctamente")

        # Seleccionar sede
        await sede.select_option("1")

        # Verificar que los campos no hayan intercambiado sus valores
        usuario_actual = await usuario.input_value()
        contrasena_actual = await contrasena.input_value()

        if usuario_actual != username or contrasena_actual != password:
            raise ValueError("Los campos de autenticación tienen valores incorrectos")

        # Ingresar
        boton = self.page.locator('input[type="button"][value="Ingresar"]')

        await boton.click()

        # Esperar menú principal
        await self.wait_for_frame('menu"', timeout=30000)

        print("Login completado")

    # --------------------------------------------------
    # NAVEGACIÓN A RESUMEN
    # --------------------------------------------------

    async def open_summary(self):
        """
        Ingresa al módulo RESUMEN.
        """

        menu_frame = await self.wait_for_frame('menu"')

        menu_resumen = menu_frame.get_by_text("RESUMEN", exact=True)

        await menu_resumen.wait_for(state="visible")
        await menu_resumen.click()

        # Esperar a que el frame contenido cargue RESUMEN.
        await self.page.wait_for_function(
            """() => {
                const frame = Array.from(window.frames)
                    .find(f => f.name === "contenido");

                return frame &&
                    frame.location.href.includes("RESUMEN");
            }""",
            timeout=30000,
        )

        frame_contenido = self.get_frame("contenido")

        await frame_contenido.get_by_text("CONSULTA DE HISTORIA", exact=True).wait_for(
            state="visible"
        )

        print("Módulo RESUMEN abierto")

        return frame_contenido

    # --------------------------------------------------
    # CONSULTA DE HISTORIA
    # --------------------------------------------------

    async def open_history_consultation(self):
        """
        Ingresa a CONSULTA DE HISTORIA.
        """

        frame_contenido = self.get_frame("contenido")

        consulta_historia = frame_contenido.get_by_text(
            "CONSULTA DE HISTORIA", exact=True
        )

        await consulta_historia.wait_for(state="visible")

        await consulta_historia.click()

        print("Clic en CONSULTA DE HISTORIA realizado")

        # Esperar a que cambie el contenido del módulo.
        await frame_contenido.wait_for_load_state("domcontentloaded", timeout=30000)

        print("URL después de ingresar:", frame_contenido.url)

        return frame_contenido

    # --------------------------------------------------
    # BUSCAR PACIENTE
    # --------------------------------------------------

    async def search_patient(
        self,
        document: str,
        type_document: str,
        date: str,
        numero_ingreso: str,
        numero_folio: str,
        output_dir: Path,
    ) -> list[DocumentResult]:
        """
        Busca al paciente, selecciona el ingreso y descarga cada tipo de
        documento de forma independiente.

        Devuelve siempre un DocumentResult por tipo (descargado, no encontrado
        o con error). Lanza PatientNotFoundError si no hay resultados o no
        existe el ingreso, y cualquier otra excepción si falla la navegación
        previa a la descarga.
        """

        # 1. Navegar a RESUMEN
        await self.open_summary()

        # 2. Entrar a CONSULTA DE HISTORIA
        await self.open_history_consultation()

        # 3. Obtener nuevamente el frame
        frame_contenido = self.get_frame("contenido")

        # 4. Localizar los campos
        campo_documento = frame_contenido.locator("#vHISCKEY")
        campo_tipo_documento = frame_contenido.locator("#vFHISTIPDOC")
        campo_fecha = frame_contenido.locator("#vFINI")
        boton_actualizar = frame_contenido.locator("#BTNACTUALIZAR")

        # 5. Esperar a que el formulario esté disponible
        await campo_documento.wait_for(state="visible", timeout=15000)
        await campo_tipo_documento.wait_for(state="visible", timeout=15000)
        await campo_fecha.wait_for(state="visible", timeout=15000)

        # 6. Ingresar documento, tipo y fecha
        await campo_documento.fill(document)
        await campo_tipo_documento.select_option(type_document)
        await campo_fecha.fill(date)

        # 7. Ejecutar búsqueda
        await boton_actualizar.wait_for(state="visible", timeout=15000)
        await boton_actualizar.click()

        print("Búsqueda del paciente ejecutada correctamente")

        # 8. Esperar resultados
        filas = frame_contenido.locator(
            "#GridContainerTbl tbody tr[id^='GridContainerRow_']"
        )

        try:
            await filas.first.wait_for(state="visible", timeout=20000)
        except PlaywrightTimeoutError:
            raise PatientNotFoundError(
                "No aparecieron resultados para el paciente consultado"
            )

        # 9. Buscar el número de ingreso
        cantidad_filas = await filas.count()
        fila_ingreso = None

        for i in range(cantidad_filas):

            fila = filas.nth(i)

            ingreso_elemento = fila.locator("[id^='span_vINGCSCG_']")

            ingreso = (await ingreso_elemento.inner_text()).strip()

            if ingreso == str(numero_ingreso):
                fila_ingreso = fila
                break

        if fila_ingreso is None:
            raise PatientNotFoundError(
                f"No se encontró el ingreso número {numero_ingreso}"
            )

        print(f"Ingreso encontrado: {numero_ingreso}")

        await fila_ingreso.locator('input[title="Confirmar"]').click()

        print("Ingreso seleccionado correctamente")

        # 10. Abrir el rango de impresión (si falla, no se puede descargar nada)
        await self.configure_folio_range(numero_folio)

        # 11. Descargar cada tipo por separado: si uno falla o no existe,
        #     los demás se siguen intentando.
        async def historia():
            archivo = await self.download_document(
                output_dir / f"{document}_{numero_ingreso}_{numero_folio}.pdf"
            )
            return [archivo]

        return [
            await self.run_step(DocumentType.FOLIO_RANGE, historia),
            await self.run_step(
                DocumentType.DISABILITIES,
                lambda: self.download_incapacities(
                    document, numero_ingreso, date, output_dir
                ),
            ),
            await self.run_step(
                DocumentType.PRESCRIPTIONS,
                lambda: self.download_prescriptions(
                    document, numero_ingreso, output_dir
                ),
            ),
            await self.run_step(
                DocumentType.MEDICAL_ORDERS,
                lambda: self.download_medical_orders(
                    document, numero_ingreso, numero_folio, output_dir
                ),
            ),
        ]

    # --------------------------------------------------
    # EJECUCIÓN AISLADA DE CADA TIPO DE DOCUMENTO
    # --------------------------------------------------

    async def run_step(self, type_document, action) -> DocumentResult:
        """
        Ejecuta la descarga de un tipo de documento y devuelve su resultado:
        - DOWNLOADED: se descargó al menos un archivo.
        - NOT_FOUND: el sistema no tiene ese documento (DocumentNotFoundError).
        - FAILED: error técnico (timeout, PDF inválido, etc.).
        """
        try:
            files = await action()

            if not files:
                return DocumentResult(
                    type_document,
                    DocumentStatus.NOT_FOUND,
                    message="No se encontraron documentos de este tipo",
                )

            return DocumentResult(
                type_document,
                DocumentStatus.DOWNLOADED,
                files=list(files),
            )

        except DocumentNotFoundError as error:

            print(f"{type_document}: {error}")

            return DocumentResult(
                type_document,
                DocumentStatus.NOT_FOUND,
                message=str(error),
            )

        except Exception as error:

            # Dejar la pantalla lista para el siguiente tipo de documento.
            await self.close_pdf_popup()

            detail = str(error).strip().splitlines()
            detail = detail[0] if detail else ""

            print(f"{type_document}: error -> {type(error).__name__}: {detail}")

            return DocumentResult(
                type_document,
                DocumentStatus.FAILED,
                message=f"{type(error).__name__}: {detail}",
            )

    async def close_pdf_popup(self, popup_id: str = "gxp1"):
        """
        Cierra el visor de PDF si quedó abierto tras un error.
        """
        try:
            frame_contenido = self.get_frame("contenido")
            popup = frame_contenido.locator(f"#{popup_id}_b")

            if await popup.is_visible():
                await frame_contenido.locator(f"#{popup_id}_cls").click()
                await popup.wait_for(state="hidden", timeout=5000)

        except Exception:
            pass

    async def wait_for_grid(self, timeout: int = 10000):
        """
        Espera a que termine la recarga de la tabla del popup, para no
        confundir una tabla que aún está cargando con "no hay documentos".
        """
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeoutError:
            pass

    async def download_document(
        self, output_path: Path, popup_id: str = "gxp1"
    ) -> Path:
        frame_contenido = self.get_frame("contenido")

        popup = frame_contenido.locator(f"#{popup_id}_b")
        await popup.wait_for(state="visible", timeout=60000)
        print("Ventana del PDF abierta")

        iframe = frame_contenido.locator(f"#{popup_id}_ifrm")
        await iframe.wait_for(state="attached", timeout=30000)

        src = await iframe.get_attribute("src")
        if not src:
            raise Exception("El iframe del PDF no tiene src")

        pdf_url = urljoin(frame_contenido.url, src)

        response = await self.page.context.request.get(pdf_url, timeout=60000)
        if not response.ok:
            raise Exception(f"Error al descargar el PDF: HTTP {response.status}")

        body = await response.body()
        if not body.startswith(b"%PDF"):
            raise Exception("La respuesta no es un PDF válido")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(body)
        print(f"PDF guardado en: {output_path}")

        await frame_contenido.locator(f"#{popup_id}_cls").click()
        await popup.wait_for(state="hidden", timeout=15000)
        print("Ventana del PDF cerrada")

        return output_path

    async def download_incapacities(
        self, document: str, numero_ingreso: int, date: str, output_dir: Path
    ) -> list[Path]:
        """
        Selecciona CERTIFICADOS MÉDICOS IESS, filtra por fecha y descarga
        todas las incapacidades de la tabla. Formato de fecha: dd/mm/yyyy.
        """
        frame_contenido = self.get_frame("contenido")
        popup_frame = frame_contenido.frame_locator("#gxp0_ifrm")

        # 1. Seleccionar CERTIFICADOS MÉDICOS IESS
        rango = popup_frame.locator("#vRANGO")
        await rango.wait_for(state="visible", timeout=20000)
        await rango.select_option("13")
        print("Opción CERTIFICADOS MÉDICOS IESS seleccionada")

        # 2. Esperar los campos de fecha
        fecha_ini = popup_frame.locator("#W0241vFCHINIINC")
        fecha_fin = popup_frame.locator("#W0241vFCHFININC")

        await fecha_ini.wait_for(state="visible", timeout=20000)
        await fecha_fin.wait_for(state="visible", timeout=20000)

        # 3. Escribir las fechas (press_sequentially respeta la máscara/validación)
        for campo in (fecha_ini, fecha_fin):
            await campo.click()
            await campo.press_sequentially(date, delay=50)
            await campo.press("Tab")

        # 4. Actualizar
        boton = popup_frame.locator("#W0241BTNACTUALIZAINC")
        await boton.wait_for(state="visible", timeout=15000)
        await boton.click()
        await self.wait_for_grid()

        # 5. Esperar la tabla; si no hay filas, no tiene incapacidades
        filas = popup_frame.locator(
            "#W0241IncpacgContainerTbl tr[id^='W0241IncpacgContainerRow_']"
        )

        try:
            await filas.first.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeoutError:
            raise DocumentNotFoundError(
                f"El paciente no tiene incapacidades para la fecha {date}"
            )

        cantidad = await filas.count()
        print(f"Incapacidades encontradas: {cantidad}")

        # 6. Descargar cada una
        archivos = []

        for i in range(cantidad):
            fila = filas.nth(i)

            consecutivo = (
                await fila.locator("[id^='span_W0241vINCCONPAC_']").inner_text()
            ).strip()

            await fila.locator('input[title="Imprimir"]').click()

            ruta = output_dir / f"{document}_{numero_ingreso}_INC_{consecutivo}.pdf"
            archivos.append(await self.download_document(ruta, popup_id="gxp1"))

        return archivos

    async def download_prescriptions(
        self, document: str, numero_ingreso: int, output_dir: Path
    ) -> list[Path]:
        """
        Selecciona PRESCRIPCION y descarga todas las formulaciones de la tabla.
        """
        frame_contenido = self.get_frame("contenido")
        popup_frame = frame_contenido.frame_locator("#gxp0_ifrm")

        # 1. Seleccionar PRESCRIPCION
        rango = popup_frame.locator("#vRANGO")
        await rango.wait_for(state="visible", timeout=20000)
        await rango.select_option("15")
        print("Opción PRESCRIPCION seleccionada")
        await self.wait_for_grid()

        # 2. Esperar la tabla; si no hay filas, no hay formulaciones
        filas = popup_frame.locator(
            "#W0241FormulaContainerTbl tr[id^='W0241FormulaContainerRow_']"
        )

        try:
            await filas.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            raise DocumentNotFoundError("El paciente no tiene formulaciones")

        cantidad = await filas.count()
        print(f"Formulaciones encontradas: {cantidad}")

        # 3. Descargar cada una
        archivos = []

        for i in range(cantidad):
            fila = filas.nth(i)

            folio = (
                await fila.locator("[id^='span_W0241CTLHISCSEC_']").inner_text()
            ).strip()

            await fila.locator('input[title="Imprimir"]').click()

            ruta = output_dir / f"{document}_{numero_ingreso}_FORM_{folio}.pdf"
            archivos.append(await self.download_document(ruta, popup_id="gxp1"))

        return archivos

    async def download_medical_orders(
        self,
        document: str,
        numero_ingreso: int,
        numero_folio: int,
        output_dir: Path,
        option_value: str = "16",
        tipo_procedimiento: str = "98",  # 98 = TODOS
    ) -> list[Path]:
        """
        Selecciona órdenes médicas, deja el tipo de procedimiento en TODOS,
        actualiza la tabla y descarga todas las órdenes del ingreso del paciente.
        """
        frame_contenido = self.get_frame("contenido")
        popup_frame = frame_contenido.frame_locator("#gxp0_ifrm")

        # 1. Seleccionar la opción de órdenes médicas
        rango = popup_frame.locator("#vRANGO")
        await rango.wait_for(state="visible", timeout=20000)
        await rango.select_option(option_value)
        print("Opción de órdenes médicas seleccionada")
        await self.wait_for_grid()

        # 2. Tipo de procedimiento: TODOS. Aparece al elegir órdenes médicas y
        #    suele venir seleccionado, pero se verifica igualmente.
        tipo = popup_frame.locator("#W0241vTIPPRC")
        await tipo.wait_for(state="visible", timeout=15000)

        if await tipo.input_value() != tipo_procedimiento:
            await tipo.select_option(tipo_procedimiento)
            await self.wait_for_grid()

            if await tipo.input_value() != tipo_procedimiento:
                raise Exception(
                    "No se pudo dejar el tipo de procedimiento en TODOS"
                )

        print("Tipo de procedimiento: TODOS")

        # 3. Actualizar la tabla
        boton = popup_frame.locator('input[name="W0241ACTUALIZA"]')
        await boton.wait_for(state="visible", timeout=15000)
        await boton.click()
        await self.wait_for_grid()

        # 4. Esperar filas de ÓRDENES (las que tienen "Tipo de Procedimiento").
        #    Esperar solo "una fila" podría aceptar filas viejas de otra tabla
        #    y dar un falso "no tiene órdenes".
        filas = popup_frame.locator(
            "#W0241FormulaContainerTbl tr[id^='W0241FormulaContainerRow_']"
        )
        celdas_tipo = popup_frame.locator(
            "#W0241FormulaContainerTbl [id^='span_W0241CTLHCPRCTIP_']"
        )

        try:
            await celdas_tipo.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            raise DocumentNotFoundError("El paciente no tiene órdenes médicas")

        # 5. Filtrar por ingreso: todas las órdenes del ingreso del paciente
        ingreso_buscado = str(numero_ingreso).strip().lstrip("0")
        cantidad = await filas.count()
        coincidentes = []

        for i in range(cantidad):
            fila = filas.nth(i)

            tipo_elemento = fila.locator("[id^='span_W0241CTLHCPRCTIP_']")

            if await tipo_elemento.count() == 0:
                continue

            ingreso = (
                await fila.locator("[id^='span_W0241CTLHCTVIN51_']").inner_text()
            ).strip().lstrip("0")

            if ingreso != ingreso_buscado:
                continue

            folio = (
                await fila.locator("[id^='span_W0241CTLHISCSEC_']").inner_text()
            ).strip()
            tipo_procedimiento_fila = (await tipo_elemento.inner_text()).strip()

            coincidentes.append((i, folio, tipo_procedimiento_fila))

        if not coincidentes:
            raise DocumentNotFoundError(
                f"No hay órdenes médicas para el ingreso {numero_ingreso}"
            )

        print(
            f"Órdenes médicas encontradas para el ingreso {numero_ingreso}: {len(coincidentes)}"
        )

        # 6. Descargar cada una
        archivos = []

        for n, (i, folio, nombre_tipo) in enumerate(coincidentes, start=1):
            print(f"Orden {n}/{len(coincidentes)}: {nombre_tipo} (folio {folio})")

            await filas.nth(i).locator('input[title="Imprimir"]').click()

            ruta = output_dir / f"{document}_{numero_ingreso}_ORD_{folio}_{n}.pdf"
            archivos.append(await self.download_document(ruta, popup_id="gxp1"))

        return archivos

    async def configure_folio_range(self, numero_folio: int):
        """
        Configura el rango de folios para imprimir la historia clínica.
        """
        frame_contenido = self.get_frame("contenido")

        # 1. Esperar a que aparezca la ventana emergente
        popup = frame_contenido.locator("#gxp0_b")

        await popup.wait_for(state="visible", timeout=30000)

        print("Ventana Rango de Impresión Historia Clínica abierta")

        # 2. Acceder al iframe interno del popup
        popup_frame = frame_contenido.frame_locator("#gxp0_ifrm")

        # 3. Esperar a que cargue el formulario
        rango = popup_frame.locator("#vRANGO")

        await rango.wait_for(state="visible", timeout=20000)

        print("Formulario de impresión cargado")

        # 4. Seleccionar RANGO DE FOLIOS
        await rango.select_option("2")

        print("Rango de folios seleccionado")

        # 5. Esperar los campos Desde y Hasta
        folio_desde = popup_frame.locator("#vFOLINI")
        folio_hasta = popup_frame.locator("#vFOLFIN")

        await folio_desde.wait_for(state="visible", timeout=15000)

        await folio_hasta.wait_for(state="visible", timeout=15000)

        # 6. Introducir el mismo folio en ambos campos
        folio = str(numero_folio)

        await folio_desde.fill(folio)
        await folio_hasta.fill(folio)

        print(f"Folio configurado: {folio} - {folio}")

        # 7. Confirmar
        boton_confirmar = popup_frame.locator("#BTNCONFIRMAR")

        await boton_confirmar.wait_for(state="visible", timeout=15000)

        await boton_confirmar.click()

        print("Rango de folios confirmado correctamente")
