import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://localhost:6335")


if not client.collection_exists(collection_name="Legaltext"):
    client.create_collection(
    collection_name="Legaltext",
    vectors_config=VectorParams(size=4, distance=Distance.COSINE),
)

def main():
    response = requests.post(
        "http://localhost:11434/api/embed",
        json={"model":"mxbai-embed-large","input":"Hello, World"},
    )
    data = response.json()
    print(data)


if __name__ == "__main__":
    main()
