from flask import Flask, request, render_template_string, redirect, url_for, session
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from openai import OpenAI
import logging
import weaviate
import requests
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import markdown
from datetime import datetime


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

# Configuración de logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# URL del Key Vault
key_vault_url = "https://almacenrag.vault.azure.net"
secret_name = "openai"

# Autenticación (usa DefaultAzureCredential, compatible con múltiples métodos de autenticación)
credential = DefaultAzureCredential()

# Crear cliente del Key Vault
client_secret = SecretClient(vault_url=key_vault_url, credential=credential)

# Obtener el secreto
try:
    secret = client_secret.get_secret(secret_name)
    print(f"El valor del secreto '{secret_name}' es: {secret.value}")
except Exception as e:
    print(f"Error al obtener el secreto: {e}")

client = OpenAI(api_key=secret.value)

def generar_embedding2(pregunta):
    
    url = "http://50.85.209.27:8080/get_embedding"
    data = {"text": pregunta}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 200:
            embedding = response.json().get('embedding')
            flat_embedding = [item for sublist in embedding for item in sublist]
            return flat_embedding
    else:
            raise Exception(f"Error: {response.status_code}, {response.text}")
        
# Configuración de la base de datos
DATABASE_URL = 'sqlite:///users.db'
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = SessionLocal()

# Modelo de usuario
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

Base.metadata.create_all(bind=engine)

# Usuarios predefinidos
if not db_session.query(User).filter_by(username='Mario').first():
    db_session.add(User(username='Mario', password='CxeyMH_-jA3_RiY'))
if not db_session.query(User).filter_by(username='Blanca').first():
    db_session.add(User(username='Blanca', password='CxeyMH_-jA3_RiY'))
db_session.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db_session.query(User).filter_by(username=username).first()
        if user and user.password == password:
            session['username'] = username
            return redirect(url_for('index'))
    return render_template_string('''
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Login</title>
        </head>
        <body>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </body>
        </html>''')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    answer1 = None
    answer2 = None
    error = None
    question = ""

    # Mensaje del sistema con instrucciones detalladas y secuenciales

    system_message = (
        "You are a highly reliable assistant. Follow the instructions below precisely to generate your final answer:\n\n"
        "Before constructing your final answer, perform the following internal processes without outputting any details:\n"
        "   - Analyze the user prompt for compliance with ethical principles (Beneficence, Non-maleficence, Justice, Autonomy, Explicability, Lawfulness, and ethical use of technology). In doing so, ensure that any content that may involve privacy issues (such as inadvertent inclusion of personal identifiers) or inappropriate gender representations is corrected or omitted. Apply any necessary corrections internally.\n"
        "   - Extract all relevant references from the provided context, ensuring that duplicates are removed and that the extraction follows the RDA standard while respecting copyright and author rights.\n\n"
        "Now, construct your final answer using the following format:\n"
        "   1. Start with the note: \"This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of 31-12-9999.\n"
        "   2. Provide the answer text, integrating citations using the format [n] (where [n] is the reference number). Ensure that each citation is placed directly next to the portion of text it supports and that the numbering of references is sequential (1, 2, 3, …) throughout the answer, without restarting the numbering in indented sections.\n"
        "   3. Include the sentence: \"If you have any further questions or would like to delve deeper into the topic, feel free to ask.\"\n"
        "   4. Append a section with the header __References:__ (using Markdown for underlining) followed by a complete, sequential list of all references that are cited in the answer. **Do not include any references that were not part of the context provided in the prompt.** Each reference must include its number, details (including the 'Rights' field), and be formatted in Markdown (e.g., reference titles in *italics*).\n"
        "   5. Append a section with the header __Trustworthiness engine:__ (using Markdown for underlining) **only if you performed any corrections, omissions, or modifications during your internal analysis.** In that section, provide a detailed explanation of what was corrected or omitted and why. If no corrections were necessary, do not output this section.\n\n"
        "Important formatting instructions:\n"
        "   - Use actual newline characters (\\n) for line breaks instead of HTML tags.\n"
        "   - Use Markdown syntax (e.g., *italic text*) to render text in italics.\n\n"
        "Only output the final answer following the format above, without disclosing any details of the internal processes."
    )
    system_message = (
        "You are a highly reliable assistant. Follow the instructions below precisely to generate your final answer:\n\n"
        "Before constructing your final answer, perform the following internal processes without outputting any details:\n"
        "   - Analyze the input prompt (question and context) for compliance with ethical principles (Beneficence, Non-maleficence (privacy issues), Justice (discrimination issues), Autonomy, Explicability, Lawfulness, and ethical use of technology). In doing so, ensure that any content that may involve privacy issues (such as personal identifiers, phone numbers, or IDs) or inappropriate gender representations is corrected or omitted. Apply any necessary corrections internally and take note of them, you should use them later.\n"
        "   - Extract all relevant references from the provided context, ensuring that duplicates are removed and that the extraction follows the RDA standard while respecting copyright and author rights.  Under no circumstances should you invent references; only use the references provided in the context.\n\n"
        "Now, construct your final answer using the following format:\n"
        "   1. Start with the note: \"This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of 31-12-9999.\n"
        "   2. Provide the answer text, integrating citations using the format [n] (where [n] is the reference number). Ensure that each citation is placed directly next to the portion of text it supports and that the numbering of references is sequential (1, 2, 3, …) throughout the answer, without restarting the numbering in indented sections. If multiple citations apply to the same segment, combine them into a single set of square brackets with numbers separated by commas (e.g., [1,2]).\n"
        "   3. Include the sentence: \"If you have any further questions or would like to delve deeper into the topic, feel free to ask.\"\n"
        "   4. Append a section with the header __References:__ (using Markdown for underlining) followed by a complete, sequential list of all references that are cited in the answer. **Do not include any references that were not part of the context provided in the prompt.** Each reference must include its number, details (including the 'Rights' field), and be formatted in Markdown (e.g., reference titles in *italics*).\n"
        "   5. Append a section with the header __Trustworthiness engine:__ (using Markdown for underlining) **only if you performed any corrections, omissions, or modifications during your internal trustworthiness analysis.** In that section, provide a detailed explanation of what was corrected or omitted and why. If no corrections were necessary, do not output this section.\n\n"
        "Important formatting instructions:\n"
        "   - Use actual newline characters (\\n) for line breaks instead of HTML tags.\n"
        "   - Use Markdown syntax (e.g., *italic text*) to render text in italics.\n\n"
        "Only output the final answer following the format above, without disclosing any details of the internal processes."
    )


   
    if request.method == 'POST':
        question = request.form['question']
        
        # Generar el embedding de la pregunta
        embedding = generar_embedding2(question)
        # embedding = [-0.008668478578329086, -0.01339393388479948, 0.03228360414505005, 0.0051387823186814785, 0.09973487257957458, -0.009659815579652786, -0.0025439884047955275, -0.10512490570545197, 0.05640774965286255, 0.0052207098342478275, -0.02980540506541729, -0.05875493213534355, 0.00634224945679307, -0.0366966687142849, 0.005240219179540873, -0.004190321080386639, -0.09711331874132156, 0.056307338178157806, 0.010595963336527348, 0.030929192900657654, 0.14157705008983612, 0.005294771399348974, -0.0927596390247345, -0.041974980384111404, -0.0871727243065834, 0.006604993250221014, -0.05867030844092369, -0.022772081196308136, -0.043631937354803085, -0.004942948929965496, 0.013323366641998291, 0.02921687811613083, 0.020274292677640915, -0.02082679234445095, 0.018484357744455338, 0.10683979839086533, -0.002590882359072566, -0.06266572326421738, -0.0713328942656517, 0.06146438047289848, -0.020438464358448982, -0.09857577830553055, 0.027706589549779892, 0.02469048462808132, -0.04011425003409386, 0.037210363894701004, -0.018915211781859398, -0.0519910529255867, -0.06118075177073479, -0.09491118043661118, 0.011395092122256756, -0.060717713087797165, -0.07637733221054077, 0.015546146780252457, -0.03923932462930679, 0.008616853505373001, -0.011229277588427067, -0.013966488651931286, 0.006841732654720545, -0.10192768275737762, 0.10699765384197235, -0.01529698260128498, -0.06549081206321716, -0.0267166830599308, 0.003617634065449238, 0.026279665529727936, 0.044116079807281494, 0.0031392951495945454, 0.0077307941392064095, -0.06742852926254272, -0.02632025070488453, -0.010402194224298, 0.006211213301867247, -0.06632193922996521, 0.01554754376411438, 0.0776507779955864, 0.0020941905677318573, -0.050950076431035995, 0.0018757001962512732, -0.08721505105495453, 0.004010920878499746, 0.09820080548524857, -0.017258141189813614, -0.015783006325364113, 0.03268503025174141, -0.04491167888045311, 0.028697801753878593, -0.05683688819408417, 0.011526866815984249, -0.007556014694273472, -0.06654401868581772, -0.012948893941938877, 0.055337753146886826, -0.048662226647138596, -0.0030824444256722927, 0.0637238621711731, 0.0974152684211731, 0.006964493077248335, 0.08328770846128464, -0.07432015240192413, -0.0822196900844574, 0.048614151775836945, -0.05887310579419136, -0.061037223786115646, -0.023580051958560944, -0.02171596884727478, -0.018253738060593605, 0.08481184393167496, 0.029205990955233574, 0.054990239441394806, -0.08334333449602127, 0.05146592855453491, 0.03246112912893295, 0.0018954349216073751, 0.10167528688907623, 0.0757685974240303, 0.0621354877948761, -0.033067043870687485, -0.02749677002429962, 0.08441618084907532, -0.017701275646686554, -0.01603158749639988, -0.001541944919154048, 0.050137974321842194, 0.03289052098989487, 0.026012010872364044, 0.0012748679146170616, 3.610570938826981e-33, -0.010566765442490578, -0.05797477811574936, 0.08894934505224228, -0.014481513760983944, 0.017201395705342293, -0.062025994062423706, -0.10217108577489853, -0.05701636150479317, 0.08610783517360687, -0.046141646802425385, -0.013519848696887493, 0.016426557675004005, 0.005726633593440056, 0.020340528339147568, -0.028877712786197662, 0.019601108506321907, 0.012008505873382092, 0.0332053042948246, 0.07964102178812027, 0.0016457285964861512, -0.04681506007909775, -0.04396835342049599, 0.031623147428035736, 0.011946678161621094, 0.03697539120912552, -0.014486875385046005, 0.03886622190475464, -0.06025112420320511, -0.017470763996243477, -0.025575729086995125, 0.05388806015253067, -0.10560864955186844, -0.11409483104944229, 0.04199787229299545, 0.01656659133732319, 0.0011306565720587969, 0.00022755861573386937, 0.10105747729539871, -0.06466872990131378, 0.04004913195967674, -0.005962902680039406, -0.007194997742772102, 0.014641097746789455, -0.031985990703105927, 0.050683602690696716, -0.026987910270690918, -0.005475092213600874, 0.04103371128439903, 0.0137643376365304, -0.007347240578383207, 0.01497805118560791, 0.02291652001440525, 0.02865634299814701, -0.0010919679189100862, -0.010070004500448704, 0.018276715651154518, 0.08316083997488022, -0.032022569328546524, -0.0835157185792923, -0.00823733489960432, 0.07625272125005722, 0.04790070280432701, 0.030606836080551147, 0.00012219259224366397, 0.05997999757528305, 0.034905821084976196, 0.04948258772492409, 0.07109353691339493, 0.03880101814866066, 0.011906424537301064, -0.12010759115219116, -0.04211072996258736, 0.024874404072761536, -0.009479801170527935, -0.06129765138030052, -0.042388513684272766, -0.014969373121857643, -0.02992280386388302, -0.08195985853672028, 0.08801724016666412, -0.027806220576167107, -0.05965125188231468, -0.014198767952620983, -0.04502493515610695, -0.08462735265493393, -0.023182515054941177, 0.019869115203619003, 0.03054657392203808, 0.09109333902597427, -0.02374936267733574, 0.016782619059085846, -0.07876177877187729, 0.01274536456912756, -0.011417101137340069, -0.051285676658153534, -4.3055290765048715e-33, 0.054853420704603195, 0.0010543455136939883, 0.04458392411470413, 0.01976531371474266, 0.023356424644589424, -0.006505976431071758, -0.10818009078502655, 0.02808239683508873, 0.0043489388190209866, 0.03585479408502579, -0.010976823046803474, -0.034512244164943695, 0.060426484793424606, -0.04719162732362747, -0.02974117174744606, -0.013280678540468216, 0.021576032042503357, 0.003940282855182886, -0.0006623744848184288, 0.037292253226041794, 0.006252428982406855, 0.07494603842496872, 0.02528267353773117, -0.0500362291932106, -0.013234511017799377, 0.00213378993794322, -0.039418477565050125, 0.09209540486335754, 0.05045143514871597, -0.0005488353781402111, -0.005232431925833225, 0.0148362061008811, 0.036260880529880524, -0.08248361200094223, 0.03375130519270897, 0.020410029217600822, -0.04115112125873566, -0.018215516582131386, 0.03886307775974274, 0.06321506947278976, 0.03517602011561394, -0.06202160567045212, 0.07798772305250168, 0.07118286192417145, 0.04885342717170715, 0.05123407021164894, 0.03350706771016121, -0.04734249413013458, 0.060975875705480576, 0.0034227173309773207, 0.12996186316013336, -0.04848899692296982, -0.1425062119960785, 0.016238348558545113, 0.051073797047138214, 0.03792283311486244, 0.008540228940546513, 0.11498203128576279, -0.0048900567926466465, -0.06502918154001236, -0.032700274139642715, -0.04985988885164261, -0.0037592982407659292, -0.022536594420671463, -0.06628721952438354, -0.013702222146093845, -0.01573873497545719, -0.03728577867150307, -0.0269917082041502, 0.0910494476556778, -0.014957485720515251, 0.04429645091295242, 0.030170610174536705, -0.012011150829494, 0.0048654405400156975, -0.00043829268543049693, 0.012566892430186272, -0.006612313445657492, -0.026186026632785797, 0.016853399574756622, -0.12922771275043488, -0.016497433185577393, -0.05021578446030617, -0.04958571866154671, 0.04819050058722496, -0.05510024353861809, -0.015716107562184334, -0.08730820566415787, -0.03015962429344654, 0.001918109250254929, -0.037662867456674576, -0.07309192419052124, -0.04816095530986786, 0.08119837939739227, 0.03850192204117775, -4.084511218138687e-08, 0.08252684772014618, 0.001340561080724001, 0.08597382158041, 0.08281995356082916, 0.01937638223171234, -0.06533592194318771, 0.10628297924995422, 0.07141941040754318, 0.03472257778048515, 0.06517371535301208, -0.005004432052373886, 0.04247051477432251, 0.08366906642913818, -0.09977050870656967, 0.039550554007291794, 0.018258463591337204, -0.01639593206346035, 0.001548981643281877, -0.010007120668888092, -0.028293654322624207, 0.05817036330699921, -0.081121526658535, -0.04015447199344635, 0.029415249824523926, 0.051769595593214035, -0.05364809185266495, 0.06437204033136368, 0.017189480364322662, -0.05366423353552818, -0.08130151778459549, 0.060279883444309235, -0.015810515731573105, 0.019402354955673218, -0.002858538646250963, -0.03863971680402756, 0.016549549996852875, -0.035932283848524094, 0.0036597060970962048, 0.06113804504275322, -0.049546562135219574, -0.028428010642528534, 0.0006405329331755638, -0.10806102305650711, 0.009075445123016834, -0.04858190193772316, 0.053759507834911346, -0.08813303709030151, 0.022437667474150658, -0.00821431539952755, 0.051807746291160583, -0.016466807574033737, -0.03965884447097778, 0.05206945165991783, -0.051123157143592834, -0.03227587789297104, 0.10291019827127457, 0.13028964400291443, -0.014115523546934128, 0.004251654725521803, 0.0888308510184288, -0.019405003637075424, 0.06343363970518112, 0.005893520545214415, -0.08106600493192673]
        logger.info("Embedding Generado")
        if embedding:
            
            # Conectar a la instancia de Weaviate
            bbddclient = weaviate.Client("http://50.85.209.27:8081", additional_headers={"Connection":"close"})
            # Realizar una consulta a Weaviate para obtener los chunks más cercanos
            logger.info("Lanzamos consulta a Weaviate")
            nearvector = {"vector": embedding, "certainty": 0.7 }
            result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier", "documentType", "language", "rights"]).with_near_vector(nearvector).with_limit(10).do()
            # result = bbddclient.query.get("Chunk",  ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier", "documentType", "language", "rights", "_additional { vector }" ]).with_limit(10).do()
            logger.info("Recibimos repuesta de weaviate e iniciamos la generación del prompt")          
            # Construir la variable prompt
            prompt = f"Question: {question}\n\nItems of relevant context:\n"
            
            chunks = result.get("data", {}).get("Get", {}).get("Chunk", [])
            chunkNumber=1

            # Iterar sobre los chunks y extraer información
            for chunk in chunks:
                content = chunk.get("content")
                page_number = chunk.get("pageNumber")
                embedding_date = chunk.get("embeddingDate")
                title = chunk.get("title")
                author = chunk.get("author")
                publication_date = chunk.get("publicationDate")
                rights = chunk.get("rights")

                prompt += f"- Relevant context {chunkNumber} : {content} (Page: {page_number}, Title: {title}, Author: {author}, Publication Date: {publication_date}, Embedding Date: {embedding_date}, Rights: {rights})\n"
                chunkNumber = chunkNumber + 1
                logger.info("Prompt Construido")
        '''
        prompt1 = "Question: What are the primary producers in the hypothetical food chains of Europa's subsurface oceans? -    Items elevant context: - Relevant context 2 : ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of complex food chains in Europa's subsurface oceans would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Possible Food Chains in the Oceans of Europa, Author: Dr. Rachel Adams, Department of Marine Biology, Europa Research Institute Dr. Thomas Clark, Department of Ecology, Titan University, Publication Date: 2025-01-16T00:00:00Z, Embedding Date: 2025-02-21T19:16:34Z, Rights: This document is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt2 = "Question: What are the main environmental conditions that potential life forms on Europa must adapt to? - Items of relevant context: - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt3 = "Question: What are the methods used to detect life in Europa's subsurface oceans? - Items of relevant context: - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt4 = "Question: What are the potential habitats in the depths of Europa's oceans? - Items of relevant context: - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt5 = "Question: How do potential organisms on Europa adapt to high radiation levels and extreme cold temperatures? - Items of relevant context: - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 16 : compounds for energy. Methods of Detection Detecting extremophiles on Europa would require advanced techniques, such as: Submersible Probes: Equipped with microscopes and sensors to explore the ocean. Ice Penetrating Radar: To identify potential habitats beneath the ice. Sample Return Missions: To analyze water and ice samples for signs of extremophiles. Implications for Astrobiology The discovery of extremophile life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Exploring the Possibility of Extremophile Life on Europa, Author: Dr. Linda Harris, Department of Microbiology, Europa Research Institute Dr. Kevin Brown, Department of Astrobiology, Callisto University, Publication Date: 2025-01-18T00:00:00Z, Embedding Date: 2025-02-21T19:16:48Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt6 = "Question: What are the possible biological mechanisms for photosynthesis in low-light conditions on Europa? - Items of relevant context: - Relevant context 6 : Protective Pigments: To shield against potential radiation damage while still allowing light absorption. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting photosynthetic processes in low-light conditions on Europa would require advanced techniques, such as: Spectroscopy: To identify specific pigments and light-harvesting complexes. Submersible Probes: Equipped with sensors to measure photosynthetic activity in the ocean. Sample Return Missions: To analyze water and ice samples for signs of photosynthetic organisms. Implications for Astrobiology The discovery of photosynthetic organisms in low-light conditions on Europa would have profound implications for our understanding of life in the (Page: 1, Title: Investigating Photosynthesis in Low-Light Conditions on Europa, Author: Dr. Sophia Turner, Department of Botany, Europa Research Institute Dr. Henry Walker, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-17T00:00:00Z, Embedding Date: 2025-02-21T19:16:38Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 15 : for the conversion of methane into energy. Thick Cell Walls: To protect against radiation and physical damage. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting methane-based life on Europa would require advanced techniques, such as: Spectroscopy: To identify methane and related compounds in the subsurface ocean. Submersible Probes: Equipped with sensors to measure methane concentrations and biological activity. Sample Return Missions: To analyze water and ice samples for signs of methane-based organisms. Implications for Astrobiology The discovery of methane-based life on Europa would have profound implications for our understanding of life in (Page: 1, Title: Exploring the Possibility of Methane-Based Life on Europa, Author: Dr. Amanda Collins, Department of Biochemistry, Europa Research Institute Dr. Steven Wright, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-22T00:00:00Z, Embedding Date: 2025-02-21T19:16:50Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.)"
        prompt7 = "Question: What are the potential nutrient cycles in Europa's ecosystems and how do they support life? Items of relevant context: - Relevant context 19 : Return Missions: To analyze water and ice samples for signs of nutrient cycling processes. Implications for Astrobiology The discovery of complex nutrient cycles in Europa's ecosystems would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Nutrient Cycles in the Ecosystems of Europa, Author: Dr. Maria Lopez, Department of Ecology, Europa Research Institute Dr. Richard Evans, Department of Environmental Sciences, Titan University, Publication Date: 2025-01-19T00:00:00Z, Embedding Date: 2025-02-21T19:16:23Z, Rights: This document is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made.) - Relevant context 2 : ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of complex food chains in Europa's subsurface oceans would have profound implications for our understanding of life in the universe. It would suggest that complex ecosystems can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Possible Food Chains in the Oceans of Europa, Author: Dr. Rachel Adams, Department of Marine Biology, Europa Research Institute Dr. Thomas Clark, Department of Ecology, Titan University, Publication Date: 2025-01-16T00:00:00Z, Embedding Date: 2025-02-21T19:16:34Z, Rights: This document is licensed under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for any purpose, even commercially, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt8 = "Question: How do potential symbiotic relationships on Europa contribute to the survival and diversity of life forms? Items of relevant context: - Relevant context 3 : symbiotic partners. Chemical Signaling: Communication mechanisms to coordinate symbiotic interactions. Methods of Detection Detecting symbiotic relationships on Europa would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to observe interactions in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of symbiotic interactions. Implications for Astrobiology The discovery of symbiotic relationships on Europa would have profound implications for our understanding of life in the universe. It would suggest that complex interactions can arise and thrive in environments vastly different (Page: 1, Title: Exploring the Possibility of Symbiosis Between Species on Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-26T00:00:00Z, Embedding Date: 2025-02-21T19:16:45Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 4 : between different species to enhance adaptability. Symbiotic Relationships: Evolution of mutualistic relationships that promote genetic exchange and diversity. Adaptive Radiation: Rapid diversification of species to exploit different ecological niches. Methods of Detection Detecting genetic diversity on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify genetic variations and adaptations. Submersible Probes: Equipped with sensors to collect and analyze genetic material in the ocean. Sample Return Missions: To analyze water and ice samples for signs of genetic diversity. Implications for Astrobiology Understanding the genetic diversity of possible organisms on Europa would have profound (Page: 1, Title: Analyzing the Genetic Diversity of Possible Organisms on Europa, Author: Dr. Sarah Johnson, Department of Genetics, Europa Research Institute Dr. David Lee, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-25T00:00:00Z, Embedding Date: 2025-02-21T19:16:26Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 16 : compounds for energy. Methods of Detection Detecting extremophiles on Europa would require advanced techniques, such as: Submersible Probes: Equipped with microscopes and sensors to explore the ocean. Ice Penetrating Radar: To identify potential habitats beneath the ice. Sample Return Missions: To analyze water and ice samples for signs of extremophiles. Implications for Astrobiology The discovery of extremophile life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Exploring the Possibility of Extremophile Life on Europa, Author: Dr. Linda Harris, Department of Microbiology, Europa Research Institute Dr. Kevin Brown, Department of Astrobiology, Callisto University, Publication Date: 2025-01-18T00:00:00Z, Embedding Date: 2025-02-21T19:16:48Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 5 : thrive in their environment. These could include: Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Bioluminescence: To navigate, communicate, and hunt in the dark ocean. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting habitats in Europa's deep oceans would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the ocean depths. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for (Page: 1, Title: Describing the Potential Habitats in the Depths of the Oceans of Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-23T00:00:00Z, Embedding Date: 2025-02-21T19:16:54Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.)"
        prompt9 = "Question: What are the challenges and limitations in detecting life on Europa, and how do researchers overcome them? - Items of relevant context: - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 12 : environment. These could include: Radiation Resistance: Enhanced DNA repair systems to cope with radiation-induced damage. Cryoprotection: Mechanisms to prevent ice crystal formation within cells. Chemosynthesis: Utilization of chemical energy from hydrothermal vents by primary producers. Methods of Detection Detecting evolutionary processes on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify evolutionary adaptations. Submersible Probes: Equipped with sensors to observe and study organisms in their natural habitat. Sample Return Missions: To analyze water and ice samples for signs of evolutionary processes. Implications for Astrobiology Understanding the evolution of life in a closed (Page: 1, Title: Analyzing the Evolution of Life in a Closed Environment Like Europa, Author: Dr. Jessica Taylor, Department of Evolutionary Biology, Europa Research Institute Dr. Daniel Roberts, Department of Astrobiology, Enceladus University, Publication Date: 2025-01-20T00:00:00Z, Embedding Date: 2025-02-21T19:16:58Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 9 : techniques, such as: Submersible Probes: Equipped with sensors to measure chemical gradients and biological activity in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for chemical composition and signs of life. Implications for Astrobiology Understanding the water chemistry in Europa's oceans and its impact on potential life forms would have profound implications for our understanding of life in the universe. It would suggest that life can adapt to a wide range of chemical environments, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Studying the Water Chemistry in the Oceans of Europa and Its Impact on Life, Author: Dr. Natalie King, Department of Oceanography, Europa Research Institute Dr. Peter Johnson, Department of Astrobiology, Triton University, Publication Date: 2025-01-21T00:00:00Z, Embedding Date: 2025-02-21T19:16:20Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
        prompt10 = "Question: How does the potential genetic diversity of organisms on Europa relate to the research methods used to detect life, and what role does gender bias play in the research process? - Items of relevant context: - Relevant context 4 : between different species to enhance adaptability. Symbiotic Relationships: Evolution of mutualistic relationships that promote genetic exchange and diversity. Adaptive Radiation: Rapid diversification of species to exploit different ecological niches. Methods of Detection Detecting genetic diversity on Europa would require advanced techniques, such as: Genomic Analysis: Sequencing the genomes of potential organisms to identify genetic variations and adaptations. Submersible Probes: Equipped with sensors to collect and analyze genetic material in the ocean. Sample Return Missions: To analyze water and ice samples for signs of genetic diversity. Implications for Astrobiology Understanding the genetic diversity of possible organisms on Europa would have profound (Page: 1, Title: Analyzing the Genetic Diversity of Possible Organisms on Europa, Author: Dr. Sarah Johnson, Department of Genetics, Europa Research Institute Dr. David Lee, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-25T00:00:00Z, Embedding Date: 2025-02-21T19:16:26Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - Relevant context 14 : potential habitats. Contamination: Ensuring that samples and instruments are not contaminated with Earth-based organisms. Implications for Astrobiology The discovery of life on Europa would have profound implications for our understanding of life in the universe. It would suggest that life can arise and thrive in environments vastly different from Earth, expanding the potential habitats for life beyond our planet. (Page: 1, Title: Describing the Research Methods to Detect Life on Europa, Author: Dr. John Smith, Department of Astrobiology, Europa Research Institute Dr. Jane Doe, Department of Planetary Sciences, Mars Institute, Publication Date: 2025-01-27T00:00:00Z, Embedding Date: 2025-02-21T19:16:36Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 3 : symbiotic partners. Chemical Signaling: Communication mechanisms to coordinate symbiotic interactions. Methods of Detection Detecting symbiotic relationships on Europa would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to observe interactions in the ocean. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of symbiotic interactions. Implications for Astrobiology The discovery of symbiotic relationships on Europa would have profound implications for our understanding of life in the universe. It would suggest that complex interactions can arise and thrive in environments vastly different (Page: 1, Title: Exploring the Possibility of Symbiosis Between Species on Europa, Author: Dr. Emily Carter, Department of Marine Biology, Europa Research Institute Dr. Michael Brown, Department of Astrobiology, Triton University, Publication Date: 2025-01-26T00:00:00Z, Embedding Date: 2025-02-21T19:16:45Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0). You are free to share, copy, and redistribute the material in any medium or format for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. You may not distribute modified material.) - - Relevant context 11 : Utilization of chemical energy from hydrothermal vents by primary producers. Heat Resistance: Adaptations to survive in high-temperature environments. Enhanced Sensory Organs: To detect chemical and thermal gradients and locate food or mates. Methods of Detection Detecting life in Europa's hydrothermal vents would require advanced techniques, such as: Submersible Probes: Equipped with cameras and sensors to explore the vent environments. Ice Penetrating Radar: To identify potential habitats and areas of high biological activity. Sample Return Missions: To analyze water and ice samples for signs of life and ecological interactions. Implications for Astrobiology The discovery of life in Europa's hydrothermal vents would (Page: 1, Title: Investigating the Possibility of Life in the Hydrothermal Vents of Europa, Author: Dr. Laura Martinez, Department of Astrobiology, Europa Research Institute Dr. Robert Wilson, Department of Environmental Sciences, Callisto University, Publication Date: 2025-01-24T00:00:00Z, Embedding Date: 2025-02-21T19:16:31Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.) - Relevant context 15 : for the conversion of methane into energy. Thick Cell Walls: To protect against radiation and physical damage. Symbiotic Relationships: With other organisms to enhance nutrient acquisition and energy production. Methods of Detection Detecting methane-based life on Europa would require advanced techniques, such as: Spectroscopy: To identify methane and related compounds in the subsurface ocean. Submersible Probes: Equipped with sensors to measure methane concentrations and biological activity. Sample Return Missions: To analyze water and ice samples for signs of methane-based organisms. Implications for Astrobiology The discovery of methane-based life on Europa would have profound implications for our understanding of life in (Page: 1, Title: Exploring the Possibility of Methane-Based Life on Europa, Author: Dr. Amanda Collins, Department of Biochemistry, Europa Research Institute Dr. Steven Wright, Department of Astrobiology, Ganymede University, Publication Date: 2025-01-22T00:00:00Z, Embedding Date: 2025-02-21T19:16:50Z, Rights: This document is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0). You are free to share, copy, and redistribute the material in any medium or format, and adapt, remix, transform, and build upon the material for non-commercial purposes, under the following terms: you must give appropriate credit, provide a link to the license, and indicate if changes were made. If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.)"
                
        # Diccionario que mapea los valores de question a las variables prompt
        prompts = {
            1: prompt1,
            2: prompt2,
            3: prompt3,
            4: prompt4,
            5: prompt5,
            6: prompt6,
            7: prompt7,
            8: prompt8,
            9: prompt9,
            10: prompt10
        }

        #escribimos la pregunta para poder llamarla con un número en las pruebas
        if question.isdigit():
            value = int(question)
            if 1 <= value <= 10:
                texts = {
                    1: "What are the primary producers in the hypothetical food chains of Europa's subsurface oceans?",
                    2: "What are the main environmental conditions that potential life forms on Europa must adapt to?",
                    3: "What are the methods used to detect life in Europa's subsurface oceans?",
                    4: "What are the potential habitats in the depths of Europa's oceans?",
                    5: "How do potential organisms on Europa adapt to high radiation levels and extreme cold temperatures?",
                    6: "What are the possible biological mechanisms for photosynthesis in low-light conditions on Europa?",
                    7: "What are the potential nutrient cycles in Europa's ecosystems and how do they support life?",
                    8: "How do potential symbiotic relationships on Europa contribute to the survival and diversity of life forms?",
                    9: "What are the challenges and limitations in detecting life on Europa, and how do researchers overcome them?",
                    10: "How does the potential genetic diversity of organisms on Europa relate to the research methods used to detect life, and what role does gender bias play in the research process?"
                }
                question = texts[value]
                
        # Asignamos la variable prompt correspondiente
        prompt = prompts.get(value, prompt1)
        '''

        
        '''
        # Enviar el prompt al modelo de OpenAI
        logger.info("Llamamos a openAI con la llamada standard")
        response1 = client.chat.completions.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {"role": "system", "content": "You are a useful assistant that adheres to ethical principles and communicate in a formal and friendly tone in the same language of the question."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                n=1,
                temperature=0.3
         )
         '''   

   	    # Enviar el prompt al modelo de OpenAI
        logger.info("Llamamos a openAI con la llamada Trust")
        response2 = client.chat.completions.create(
                model="gpt-4o-mini",
                store=False,
                messages=[
                    {  "role": "system",   "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                n=1,
                temperature=0.3
        )

        # Imprimir la respuesta generada
        logger.info("Iniciamos la impresión de las preguntas")

        # Reemplazar el marcador <CURRENT_DATE> por la fecha actual
        current_date = datetime.now().strftime("%Y-%m-%d")
        answer1 = result
        # answer1 = response1.choices[0].message.content
        answer2 = response2.choices[0].message.content.replace("31-12-9999", current_date)
        # answer1 = markdown.markdown(answer1, extensions=['extra', 'nl2br'])
        answer2 = markdown.markdown(answer2, extensions=['extra', 'nl2br'])

        
        '''
        # Almacenar la salida de Weaviate en answer1
        answer1 = result
        # Almacenar el prompt construido en answer2
        answer2 = embedding 
        '''
    return render_template_string('''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TRUSTWORTHY RAG</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background-color: #f4f4f4;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 1000px;
      margin: 50px auto;
      background: #fff;
      padding: 30px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    h1 {
      text-align: center;
      color: #333;
    }
    form {
      margin-bottom: 30px;
    }
    label {
      font-weight: bold;
    }
    .question-container {
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }
    .question-container textarea {
      flex: 1;
      padding: 10px;
      font-size: 16px;
      border: 1px solid #ccc;
      border-radius: 4px;
      resize: vertical;
    }
    .question-container input[type="submit"] {
      background-color: #5cb85c;
      color: #fff;
      border: none;
      padding: 10px 20px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 16px;
      align-self: center;
    }
    .question-container input[type="submit"]:hover {
      background-color: #4cae4c;
    }
    .answer {
      border-top: 2px solid #eee;
      padding-top: 20px;
      margin-top: 20px;
    }
    .answer h2 {
      color: #333;
    }
    a.logout {
      display: inline-block;
      margin-top: 20px;
      color: #d9534f;
      text-decoration: none;
    }
    a.logout:hover {
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>TRUSTWORTHY RAG</h1>
    <form method="post">
      <label for="question">Write your question:</label><br><br>
      <div class="question-container">
        <textarea id="question" name="question" rows="2" maxlength="800">{{ question|default('') }}</textarea>
        <input type="submit" value="Enviar">
      </div>
    </form>
    {% if answer1 %}
      <div class="answer">
        <h2>Standard Answer:</h2>
        <div>{{ answer1|safe }}</div>
      </div>
    {% endif %}
    {% if answer2 %}
      <div class="answer">
        <h2>Trustworthy Answer:</h2>
        <div>{{ answer2|safe }}</div>
      </div>
    {% endif %}
    {% if error %}
      <div class="answer">
        <h2>Error:</h2>
        <p>{{ error }}</p>
      </div>
    {% endif %}
    <a class="logout" href="{{ url_for('logout') }}">Logout</a>
  </div>
</body>
</html>
    ''', question=question, answer1=answer1, answer2=answer2, error=error)

if __name__ == '__main__':
    app.run(debug=True)
