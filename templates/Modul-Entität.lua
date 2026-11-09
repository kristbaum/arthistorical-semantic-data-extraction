-- Modul:Entität — markiert eine Entität im Artikeltext (Bauwerk, Raum,
-- Person, Deckenbild) für die strukturierten Daten und zeigt beim Überfahren
-- ein Popover. Jede Entität wird nur einmal markiert (erste Nennung).
-- Aufruf über Vorlage:Entität:
--   {{Entität|Pfarrkirche|rolle=Bauwerk}}
--   {{Entität|Johann Adam Schöpf|rolle=Maler}}
--   {{Entität|A<sub>2</sub>|rolle=Deckenbild|titel=Gericht|bild=Band01_chunk001_p011_img002.jpg}}
--   {{Entität|1=…|rolle=Bauwerk|qid=Q123}}   (1= wenn der Text ein »=« enthält)
-- Parameter:
--   1      markierter Text, unverändert wie gedruckt (wird so angezeigt)
--   rolle  Bauwerk, Raum, Auftraggeber, Maler, Stuckateur, Baumeister, Stecher,
--          Kistler, Vergolder, Person, Deckenbild
--   titel  nur Deckenbild: Bildtitel ohne Bildfeld-Kürzel (nicht angezeigt,
--          nur im Popover und für die Datenübernahme)
--   bild   nur Deckenbild: Dateiname ohne »Datei:«; der Text verlinkt darauf
--   qid    Wikidata-Item; wird von der Wikidata-Extraktion gesetzt
--   id     interne, eindeutige Kennung (8 Zeichen a-z0-9), automatisch vergeben;
--          verbindet die Stelle mit den Aussagen der Wikidata-Extraktion.
--          Wird nicht angezeigt, nur als data-id ausgegeben.
-- Skelett: Das Popover zeigt Bezeichnung und Beschreibung aus Wikidata (falls
-- qid gesetzt und UnlinkedWikibase verfügbar), sonst den Titel, dazu Rolle,
-- Bild und Wikidata-Link. Ohne titel, bild und qid kein Popover.

local p = {}

local STYLESHEET = 'Vorlage:Entität/styles.css'
local LANGS = { 'de', 'mul', 'en' }

local function trim(s)
	if s == nil then return nil end
	s = mw.text.trim(s)
	return s ~= '' and s or nil
end

-- Wikidata-Entität über UnlinkedWikibase, oder nil (Erweiterung fehlt,
-- Entität nicht im Cache, ungültige qid).
local function getEntity(qid)
	local uwb = mw.ext and mw.ext.UnlinkedWikibase
	if not uwb then return nil end
	-- Abhängigkeit registrieren: Seite wird neu geparst, wenn die Daten kommen
	pcall(uwb.getLocalTitle, qid)
	local ok, entity = pcall(uwb.getEntity, qid)
	return ok and entity or nil
end

local function firstText(map)
	if not map then return nil end
	for _, l in ipairs(LANGS) do
		local v = map[l]
		if v and v.value and v.value ~= '' then return v.value end
	end
	return nil
end

local function popoverBody(rolle, titel, bild, qid)
	local rows = {}
	local entity = qid and getEntity(qid)
	local label = entity and firstText(entity.labels)
	local heading = label or titel
	if heading then
		table.insert(rows, '<span class="ent-title">' .. mw.text.nowiki(heading) .. '</span>')
	end
	local desc = entity and firstText(entity.descriptions)
	if desc then
		table.insert(rows, '<span class="ent-desc">' .. mw.text.nowiki(desc) .. '</span>')
	end
	if rolle then
		table.insert(rows, '<span class="ent-role">' .. mw.text.nowiki(rolle) .. '</span>')
	end
	if bild then
		table.insert(rows, '<span class="ent-image">[[Datei:' .. bild .. '|160px|link=Datei:' .. bild .. ']]</span>')
	end
	if qid then
		table.insert(rows, '<span class="ent-links">[https://www.wikidata.org/wiki/' ..
			mw.uri.encode(qid, 'PATH') .. ' Wikidata ' .. mw.text.nowiki(qid) .. ']</span>')
	end
	return table.concat(rows)
end

function p.render(frame, args)
	local text = args[1] or ''
	local rolle = trim(args.rolle)
	local titel = trim(args.titel)
	local bild = trim(args.bild)
	local qid = trim(args.qid)
	local ref = trim(args.id)
	if bild then
		bild = bild:gsub('^[Ff]ile:', '')
		bild = bild:gsub('^Datei:', '')
	end
	if qid and not qid:match('^Q%d+$') then qid = nil end

	local anchor = text
	if bild then
		anchor = '[[:Datei:' .. bild .. '|' .. text .. ']]'
	end

	local class = 'ent'
	local attrs = {}
	if rolle then
		local slug = mw.ustring.lower(rolle):gsub('[^%w]', '')
		class = class .. ' ent-' .. slug
		table.insert(attrs, 'data-rolle="' .. mw.text.encode(rolle) .. '"')
	end
	if titel then table.insert(attrs, 'data-titel="' .. mw.text.encode(titel) .. '"') end
	if qid then table.insert(attrs, 'data-qid="' .. qid .. '"') end
	if ref and ref:match('^[a-z0-9]+$') then table.insert(attrs, 'data-id="' .. ref .. '"') end
	table.insert(attrs, 1, 'class="' .. class .. '"')

	local out = '<span ' .. table.concat(attrs, ' ') .. '><span class="ent-anchor">' .. anchor .. '</span>'
	if qid or bild or titel then
		out = out .. '<span class="ent-popover">' .. popoverBody(rolle, titel, bild, qid) .. '</span>'
	end
	out = out .. '</span>'

	return frame:extensionTag('templatestyles', '', { src = STYLESHEET }) .. out
end

function p.main(frame)
	return p.render(frame, frame:getParent().args)
end

return p
