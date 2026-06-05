import discord

# Store original descriptors and methods
_orig_init = discord.Embed.__init__
_orig_add_field = discord.Embed.add_field
_orig_set_footer = discord.Embed.set_footer
_orig_set_author = discord.Embed.set_author
_orig_desc_desc = discord.Embed.description
_orig_title_desc = discord.Embed.title

def _safe_truncate_value(value: str) -> str:
    if not isinstance(value, str):
        value = str(value)
    if len(value) <= 1024:
        return value
    if value.startswith("```") and value.endswith("```"):
        first_nl = value.find("\n")
        if first_nl != -1 and first_nl < 15:
            lang = value[:first_nl]  # e.g., "```json"
            content = value[first_nl:len(value)-3]
            suffix = "\n... (truncated)\n```"
            allowed_len = 1024 - len(lang) - len(suffix)
            if allowed_len > 0:
                return f"{lang}{content[:allowed_len]}{suffix}"
        suffix = "\n...```"
        return value[:1024 - len(suffix)] + suffix
    else:
        return value[:1021] + "..."

def _safe_truncate_name(name: str) -> str:
    if not isinstance(name, str):
        name = str(name)
    if len(name) <= 256:
        return name
    return name[:253] + "..."

def _safe_truncate_description(description: str) -> str:
    if not description:
        return description
    if not isinstance(description, str):
        description = str(description)
    if len(description) <= 4096:
        return description
    return description[:4093] + "..."

def _safe_truncate_title(title: str) -> str:
    if not title:
        return title
    if not isinstance(title, str):
        title = str(title)
    if len(title) <= 256:
        return title
    return title[:253] + "..."

# Custom property/descriptors
class SafeDescription:
    def __get__(self, instance, owner):
        if instance is None:
            return self
        return _orig_desc_desc.__get__(instance, owner)
    def __set__(self, instance, value):
        value = _safe_truncate_description(value)
        _orig_desc_desc.__set__(instance, value)

class SafeTitle:
    def __get__(self, instance, owner):
        if instance is None:
            return self
        return _orig_title_desc.__get__(instance, owner)
    def __set__(self, instance, value):
        value = _safe_truncate_title(value)
        _orig_title_desc.__set__(instance, value)

# Replacement functions
def patch_embed_init(self, *args, **kwargs):
    if "title" in kwargs and kwargs["title"]:
        kwargs["title"] = _safe_truncate_title(kwargs["title"])
    if "description" in kwargs and kwargs["description"]:
        kwargs["description"] = _safe_truncate_description(kwargs["description"])
    _orig_init(self, *args, **kwargs)

def patch_embed_add_field(self, *, name, value, inline=True):
    name = _safe_truncate_name(name)
    value = _safe_truncate_value(value)
    _orig_add_field(self, name=name, value=value, inline=inline)

def patch_embed_set_footer(self, *, text=None, icon_url=None):
    if text:
        if not isinstance(text, str):
            text = str(text)
        if len(text) > 2048:
            text = text[:2045] + "..."
    return _orig_set_footer(self, text=text, icon_url=icon_url)

def patch_embed_set_author(self, *, name, url=None, icon_url=None):
    if name:
        if not isinstance(name, str):
            name = str(name)
        if len(name) > 256:
            name = name[:253] + "..."
    return _orig_set_author(self, name=name, url=url, icon_url=icon_url)

# Apply patches to discord.Embed
discord.Embed.__init__ = patch_embed_init
discord.Embed.description = SafeDescription()
discord.Embed.title = SafeTitle()
discord.Embed.add_field = patch_embed_add_field
discord.Embed.set_footer = patch_embed_set_footer
discord.Embed.set_author = patch_embed_set_author
