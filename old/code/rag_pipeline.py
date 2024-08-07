from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain import hub
from langchain_community.llms import Ollama


DATA_PATH = "../data/muenchen_en/"
MODEL = "wizardlm2:latest"

# Load data from directory
loader = DirectoryLoader(DATA_PATH, show_progress=True)
docs = loader.load()

# Define a text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
data_split = text_splitter.split_documents(docs)
print("Data Split")

# Define embeddings
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Vector Database
db = FAISS.from_documents(data_split, embeddings)
retriever = db.as_retriever()
print("Data load in vector DB successfull")

# Retrieve ollama model from pulled model
prompt = hub.pull("rlm/rag-prompt")
llm = Ollama(model=MODEL)
print("Model load successfull")

llm_2 = Ollama(model="phi")


rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

rag_chain_2 = (
     {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
