import secrets

def main():
    print("=== Cryptographic Secret Generator for Houmi Studio Production ===")
    print()
    print("HOUMI_JWT_SECRET=" + secrets.token_urlsafe(48))
    print("HOUMI_WORKER_SHARED_SECRET=" + secrets.token_hex(32))
    print("POSTGRES_PASSWORD=" + secrets.token_hex(16))
    print("REDIS_PASSWORD=" + secrets.token_hex(16))
    print()
    print("Copy the values above into your .env or docker-compose.yml configuration.")

if __name__ == "__main__":
    main()
