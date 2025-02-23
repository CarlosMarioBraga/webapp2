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
        "   - Analyze the user prompt for compliance with ethical principles (Beneficence, Non-maleficence, Justice, Autonomy, Explicability, Lawfulness, and ethical use of technology). Correct any issues internally.\n"
        "   - Extract all relevant references from the provided context, ensuring that duplicates are removed and that the extraction follows the RDA standard while respecting copyright and author rights.\n\n"
        "Now, construct your final answer using the following format:\n"
        "   1. Start with the note: \"This content was generated with artificial intelligence. Please note that the information provided is based on the latest available data as of <<<CURRENT_DATE>>>.\" (Replace <<<CURRENT_DATE>>> with the actual current date.)\n"
        "   2. Provide the answer text, integrating citations using the format [n] (where [n] is the reference number). Ensure that each citation is placed directly next to the portion of text it supports and that the numbering of references is sequential (1, 2, 3, …) throughout the answer, without restarting the numbering in indented sections.\n"
        "   3. Include the sentence: \"If you have any further questions or would like to delve deeper into the topic, feel free to ask.\"\n"
        "   4. Append a section with the header __References:__ (using Markdown for underlining) followed by a complete, sequential list of all references that are cited in the answer. **Do not include any references that were not part of the context provided in the prompt.** Each reference must include its number, details (including the 'Rights' field), and be formatted in Markdown (e.g., reference titles in *italics*).\n"
        "   5. Append a section with the header __Trustworthiness engine:__ (using Markdown for underlining) **only if you performed any corrections, omissions, or modifications during your internal analysis.** In that section, provide a detailed explanation of what was corrected or omitted and why. If no corrections were necessary, do not output this section.\n\n"
        "Important formatting instructions:\n"
        "   - Use actual newline characters (\\n) for line breaks instead of HTML tags.\n"
        "   - Use Markdown syntax (e.g., *italic text*) to render text in italics.\n\n"
        "Only output the final answer following the format above, without disclosing any details of the internal processes."
    )

   
    if request.method == 'POST':
        question = request.form['question']
        
        # Generar el embedding de la pregunta
        # embedding = generar_embedding2(question)
        embedding = [-0.0012523968471214175, 0.02259148843586445, 0.007567939348518848, 0.01839042268693447, 0.11758670210838318, 0.020330751314759254, -0.053218722343444824, 0.05403035879135132, 0.02619190886616707, -0.03153737261891365, 0.007846303284168243, -0.16025395691394806, -0.007261669263243675, 0.01889711245894432, 0.021148143336176872, 0.027392607182264328, -0.04718116298317909, 0.033843327313661575, -0.07262701541185379, 0.0615248903632164, 0.049412693828344345, -0.023459753021597862, -0.053970616310834885, 0.005571635905653238, -0.13238124549388885, 0.014244716614484787, 0.004388060420751572, 0.017939437180757523, -0.04011555388569832, -0.019484128803014755, -0.012306840158998966, -0.019481953233480453, 0.05339016392827034, -0.0268267635256052, 0.010293614119291306, 0.06496644765138626, -0.0024024269077926874, -0.08769702911376953, -0.0329374261200428, -0.05029885843396187, -0.03164173290133476, -0.05513348802924156, -0.0445244275033474, 0.016348736360669136, 0.009664352983236313, -0.011726907454431057, 0.03627781197428703, -0.022970011457800865, -0.12262696027755737, -0.011320783756673336, 0.010531065985560417, -0.001856501679867506, -0.04619379714131355, 0.003743349574506283, -0.03769189491868019, -0.032516345381736755, -0.05330444872379303, 0.034458260983228683, 0.030294856056571007, -0.05162198841571808, 0.1355632245540619, 0.01375234592705965, 0.04477814584970474, -0.026547066867351532, -0.04208283871412277, -0.024580128490924835, 0.011507517658174038, 0.01772361621260643, -0.004614689387381077, 0.02047344110906124, -0.04079044237732887, -0.06296378374099731, -0.06632687896490097, -0.01815054379403591, 0.05185168609023094, 0.0933970957994461, -0.031054140999913216, -0.05798223987221718, 0.0033843093551695347, -0.016445288434624672, 0.03010660782456398, 0.013945299200713634, 0.0005248915404081345, 0.03133050724864006, 0.03048105537891388, -0.038573481142520905, 0.08156149089336395, -0.06239224597811699, 0.00730934739112854, 0.08075260370969772, -0.05204400420188904, -0.06946183741092682, -0.019230712205171585, -0.024792855605483055, -0.04816628247499466, 0.08980878442525864, -0.012666179798543453, -0.057825490832328796, -0.011121861636638641, -0.06065140664577484, -0.0378127284348011, 0.018936878070235252, -0.00462472066283226, 0.030432138592004776, 0.022715235128998756, -0.10554514825344086, 0.009830291382968426, 0.04380412772297859, -0.0036959669087082148, -0.01708986982703209, -0.017790986225008965, -0.04477740079164505, 0.035938385874032974, -0.06355936080217361, 0.031910013407468796, -0.0036414023488759995, -0.02949409745633602, -0.11512591689825058, 0.028936151415109634, 0.020540639758110046, 0.0177101269364357, 0.0132614029571414, -0.037585318088531494, 0.09362780302762985, 0.03635478392243385, 0.06350252032279968, -0.06459813565015793, 5.004428793677863e-33, 0.0019246686715632677, -0.031598880887031555, 0.06409426778554916, 0.03690893203020096, 0.05377385392785072, -0.09494994580745697, -0.012114856392145157, -0.05921103060245514, -0.026119602844119072, -0.06714192777872086, -0.05613621324300766, -0.017772072926163673, 0.03852762654423714, 0.095943383872509, 0.03851255029439926, 0.08157728612422943, -0.012640481814742088, 0.00018252477457281202, 0.0026025164406746626, -0.002253331243991852, -0.002223215764388442, -0.03325324133038521, 0.07988731563091278, 0.004992252681404352, 0.05305611714720726, 0.04494886472821236, 0.022739900276064873, -0.061036739498376846, 0.026363667100667953, -0.04409133642911911, -0.01772942766547203, -0.14549854397773743, -0.06677170097827911, 0.04056404158473015, 0.024096742272377014, 0.10253313928842545, -0.030658431351184845, 0.00671356450766325, -0.06359869241714478, 0.004903669003397226, 0.028052544221282005, 0.025404267013072968, 0.08000463992357254, -0.032711248844861984, 0.08991146087646484, -0.015651287510991096, 0.0010397378355264664, 0.019031880423426628, -0.07065549492835999, -0.0869101732969284, 0.011125740595161915, 0.007262848783284426, 0.017876554280519485, 0.008923027664422989, 0.03815077990293503, 0.029943320900201797, 0.009485160931944847, 0.02815481647849083, -0.05700879916548729, 0.02152705192565918, -0.005990219302475452, -0.05376618728041649, 0.014225554652512074, 0.03478061407804489, 0.1158166378736496, 0.0718625858426094, -0.003826084779575467, 0.004880438093096018, -0.04564229026436806, -0.04009369760751724, -0.07662016153335571, -0.02927384525537491, 0.10164137929677963, -0.02966183051466942, -0.045883916318416595, -0.020056284964084625, -0.0232250839471817, -0.05773317068815231, -0.032261598855257034, 0.07204829901456833, -0.02883334457874298, -0.0050128367729485035, -0.011637162417173386, -0.03517942875623703, -0.09542276710271835, -0.006604173220694065, 0.019337153062224388, -0.0010676184901967645, 0.0867929458618164, -0.004010921344161034, 0.09298794716596603, -0.0688231959939003, -0.0647052451968193, 0.05193173885345459, -0.05502380430698395, -6.180600155777827e-33, 0.043274495750665665, -0.061104800552129745, 0.0525052510201931, -0.09257896989583969, -0.004193592816591263, 0.16800571978092194, -0.18917229771614075, -0.0032556846272200346, -0.04573063924908638, -0.03669070452451706, -0.007444452960044146, -0.014464112929999828, 0.037398744374513626, -0.07903493195772171, -0.08824823051691055, -0.005458145868033171, -0.02194405533373356, 0.03445319086313248, 0.07359880954027176, 0.04587167128920555, 0.017676355317234993, 0.04465333744883537, -0.0487808994948864, 0.04538207873702049, -0.00959005393087864, 0.01819879189133644, -0.021641669794917107, 0.01809188537299633, -0.028723541647195816, -0.008870112709701061, -0.07310550659894943, 0.006713172886520624, -0.015135956928133965, -0.002425871789455414, 0.04693426564335823, 0.07467087358236313, -0.012391499243676662, -0.031086768954992294, 0.033168260008096695, 0.07787797600030899, -0.003456207923591137, -0.04019990190863609, 0.0167352557182312, 0.06628091633319855, 0.1415192037820816, 0.05036593973636627, 0.0014262826880440116, -0.047548431903123856, 0.04839571565389633, 0.010686912573873997, 0.06436567008495331, -0.045595932751894, -0.10836025327444077, -0.019413771107792854, 0.05269978195428848, -0.056436602026224136, -0.02429196983575821, 0.05675289407372475, 0.056799206882715225, -0.056537970900535583, -0.037663474678993225, -0.0695425271987915, 0.038501378148794174, 0.028501728549599648, -0.07162359356880188, 0.0017571827629581094, -0.07788418233394623, 0.0625929906964302, -0.09282243996858597, 0.04218430444598198, 0.10504131019115448, 0.024958133697509766, 0.0004916138714179397, -0.028473369777202606, 0.05079754814505577, -0.058472614735364914, -0.03223498910665512, -0.004929718095809221, -0.006379954516887665, 0.054685138165950775, -0.08369924873113632, -0.04063057526946068, 0.047149647027254105, -0.00184523721691221, 0.10311057418584824, -0.047074899077415466, -0.007809991482645273, -0.051692135632038116, 0.01614440605044365, -0.03378596156835556, -0.06444286555051804, -0.08855558186769485, -0.03761137276887894, 0.04658119007945061, 0.019650379195809364, -4.222001237508266e-08, 0.10169042646884918, 0.020749974995851517, 0.02001110278069973, 0.022417418658733368, -0.026734158396720886, 0.008386093191802502, 0.00365896662697196, 0.05665939301252365, -0.06715338677167892, 0.03289388120174408, -0.012504900805652142, 0.01710633747279644, 0.10612782090902328, 0.009329603053629398, 0.06843110918998718, 0.08054780960083008, 0.04589581862092018, -0.003054768778383732, 0.022187836468219757, 0.04284460470080376, -0.0382632315158844, 0.01777189038693905, -0.03263775631785393, -0.012279530055820942, -0.0036777628120034933, -0.019635573029518127, 0.08644872158765793, -0.03898359835147858, 0.03929741308093071, -0.04149506241083145, -0.010648402385413647, -0.0451878197491169, 0.03251080960035324, 0.023163141682744026, -0.008222679607570171, 0.038299549371004105, -0.06093393266201019, -0.016286803409457207, -0.023618582636117935, 0.05201971158385277, -0.0407007597386837, 0.025342179462313652, -0.11734850704669952, -0.0005424431292340159, 0.003957665991038084, 0.07080317288637161, -0.001543775200843811, -0.020431043580174446, -0.05781259387731552, 0.0027244901284575462, 0.026548396795988083, -0.048636894673109055, 0.05804232135415077, -0.03941738232970238, -0.03901960700750351, 0.0417201966047287, 0.07089082151651382, 0.06577374041080475, 0.013577873818576336, 0.10297524929046631, 0.020349370315670967, 0.062137603759765625, 0.016088785603642464, 0.007625316735357046]
        logger.info("Embedding Generado")
        if embedding:
            
            # Conectar a la instancia de Weaviate
            bbddclient = weaviate.Client("http://50.85.209.27:8081", additional_headers={"Connection":"close"})
            # Realizar una consulta a Weaviate para obtener los chunks más cercanos
            logger.info("Lanzamos consulta a Weaviate")
            nearvector = {
                "vector": embedding , "certainty": 0
            }
            result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_near_vector(nearvector).with_limit(10).do()
            # result = bbddclient.query.get("Chunk", ["content", "pageNumber", "embeddingModel", "embeddingDate"]).with_near_vector(nearvector).do()
            # result = bbddclient.query.get("Chunk",  ["vector", "content", "pageNumber", "embeddingModel", "embeddingDate", "title", "author", "publicationDate", "identifier",  "documentType", "language", "rights"]).with_limit(1).do()
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
        
        answer1 = response1.choices[0].message.content
        answer2 = response2.choices[0].message.content.replace("31-12-9999", current_date)
        answer1 = markdown.markdown(answer1, extensions=['extra', 'nl2br'])
        answer2 = markdown.markdown(answer2, extensions=['extra', 'nl2br'])

        
        '''
        # Almacenar la salida de Weaviate en answer1
        answer1 = result
        # Almacenar el prompt construido en answer2
        answer2 = embedding 
        
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
