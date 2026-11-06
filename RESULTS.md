(greeting)
Agente [greeting]: ¡Hola! Soy el agente de tarjetas del Banco Demo. ¿En qué puedo ayudarte hoy con tus tarjetas de crédito?
  (2364 ms, 624 tokens de entrada, 110 de salida)

(product_question)
Agente [product_question]: En términos generales, las diferencias entre una tarjeta Clásica y una Platinum son:

- Público y línea de crédito: la Clásica es para uso básico; la Platinum está dirigida a clientes con mayor consumo y suele ofrecer límites más altos.
- Cuota anual: la Platinum normalmente tiene una cuota anual mayor que la Clásica.
- Beneficios y privilegios: la Platinum incluye más beneficios (mayor acumulación de puntos/millas, promociones exclusivas, acceso a salas VIP, concierge en algunos casos) que la Clásica.
- Seguros y coberturas: la Platinum suele ofrecer seguros adicionales y coberturas más amplias (viajes, accidentes, protección de compras, extensión de garantía).
- TEA/TCEA y comisiones: varían por producto y perfil; los valores exactos están en la ficha de producto.
  (12298 ms, 389 tokens de entrada, 762 de salida)

(data_query)
Agente [data_query]: Por seguridad no puedo ver tu línea disponible desde aquí. Puedes consultarla de estas formas: 1) App Banco Demo: inicia sesión > Mis tarjetas > selecciona la tarjeta > ver línea disponible. 2) Banca por Internet: ingresa a tu cuenta > Tarjetas. 3) Estado de cuenta mensual. 4) Llamando a nuestra atención al cliente o en una sucursal (sin compartir datos sensibles aquí). ¿Cuál opción prefieres para guiarte paso a paso?
  (5814 ms, 715 tokens de entrada, 571 de salida)

(sensitive_action)
 Agente [sensitive_action]: Perfecto, Paul. Un aumento de línea requiere confirmación y evaluación antes de ejecutarlo; no puedo realizarlo directamente desde aquí. Puedo guiarte para iniciar la solicitud por uno de estos canales:

- App Banco Demo: Menú > Solicitudes/Servicios > Aumento de línea (adjunta documentos). 
- Banca por Internet: Inicia sesión > Tarjetas > Solicitar aumento. 
- Llamando al Call Center o en una sucursal: un ejecutivo iniciará la gestión y te pedirá datos.

Documentos y datos que suelen pedir: comprobante de ingresos reciente (boletas o declaración), identificación vigente, datos laborales (empresa y antigüedad) y, si corresponde, extractos bancarios. El banco realizará una evaluación (historial crediticio y capacidad de pago) y te comunicará el resultado por los canales registrados. 

No compartas números de tarjeta ni DNI en este chat. ¿Por qué canal prefieres que te guíe para iniciar la solicitud?
  (8411 ms, 836 tokens de entrada, 747 de salida)

(out_of_scope)
Agente [out_of_scope]: No puedo proporcionar la cotización del dólar en tiempo real aquí. Para consultarla puedes: 1) usar la App o web del Banco Demo (sección “Tasas” o “Divisas”), 2) visitar el sitio del Banco Central de Reserva del Perú (BCRP), o 3) buscar “dólar hoy” en un buscador. ¿Quieres que te guíe para verlo en la app del Banco Demo?
  (4265 ms, 1062 tokens de entrada, 370 de salida)




Preguntas
================
¿gpt-5-mini o gpt-5-nano para clasificar intención? ¿Qué pasa con la latencia y la calidad?
gpt-5-nano tiene menos latencia y en calidad es inferior a gpt-5-mini

¿Cuánto cuesta por mes un MAX_TURNS=10 frente a MAX_TURNS=4, con el tráfico esperado?
Asumiendo 10 millones de conversaciones al mes que llegan todas al tope de turnos (peor caso), con un system prompt de 2,000 tokens y turnos de 200 tokens de entrada y 300 de salida, donde cada turno reenvía todo el historial, pasar de MAX_TURNS=4 a MAX_TURNS=10 multiplica el costo por ~3.2x porque el input crece de forma cuadrática: con GPT-5 mini va de ~$53K a ~$171K al mes, y con GPT-5 nano de ~$11K a ~$34K. El costo real dependerá de cuántas conversaciones lleguen efectivamente al tope, por lo que estos números son una cota superior.

¿Conviene un modelo chico para greeting y out_of_scope, y uno grande solo para el resto?
Si, por reduccion de costos