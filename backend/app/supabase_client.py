
from supabase import create_client, Client
from .config import settings

admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key
)

auth_client: Client = create_client(
    settings.supabase_url,
    settings.supabase_anon_key
)
