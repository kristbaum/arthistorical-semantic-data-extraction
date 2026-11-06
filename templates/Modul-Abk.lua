-- Modul:Abk — Abkürzungen mit Tooltip (<abbr>) aus Modul:Abk/Daten.
-- Aufruf über Vorlage:Abk:
--   {{Abk|LHs}}              → LHs mit Tooltip »Langhaus«
--   {{Abk|Bd|Bde.}}          → zeigt »Bde.«, Tooltip von »Bd«
--   {{Abk|Z|typ=Bildfeld}}   → Bildfeld-Kürzel (Zwickelbilder)
-- Bibliographische Kurztitel verlinken zusätzlich auf
-- [[Zur Benutzung#Bibliographische Abkürzungen]].
-- Unbekannte Kürzel erscheinen unverändert in [[Kategorie:Unbekannte Abkürzung]].

local p = {}
local data = mw.loadData('Modul:Abk/Daten')

local BIBL_ZIEL = 'Zur Benutzung#Bibliographische Abkürzungen'

local function abbr(shown, full)
	return '<abbr title="' .. mw.text.encode(full) .. '">' .. shown .. '</abbr>'
end

function p.render(key, shown, typ)
	key = mw.text.trim(key or '')
	shown = (shown and shown ~= '') and shown or key
	if typ and mw.ustring.lower(typ) == 'bildfeld' then
		local full = data.bildfeld[key]
		if full then
			return abbr(shown, full)
		end
	else
		local e = data.abk[key]
		if e then
			if e.typ == 'bibl' then
				return '[[' .. BIBL_ZIEL .. '|' .. abbr(shown, e.voll) .. ']]'
			end
			return abbr(shown, e.voll)
		end
	end
	if mw.title.getCurrentTitle().namespace == 0 then
		return shown .. '[[Kategorie:Unbekannte Abkürzung]]'
	end
	return shown
end

function p.main(frame)
	local args = frame:getParent().args
	return p.render(args[1], args[2], args.typ)
end

return p
