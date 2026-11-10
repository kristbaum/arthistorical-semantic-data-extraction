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
-- Popover: Bezeichnung und Beschreibung aus Wikidata (falls qid gesetzt und
-- UnlinkedWikibase verfügbar), sonst den Titel, dazu Rolle, Bild und
-- Wikidata-Link. Mit qid außerdem die wichtigsten Angaben je nach Art (aus
-- der Rolle, sonst P31 = Mensch):
--   Person    Geburt (P569, P19), Tod (P570, P20), Wirkungsort (P937),
--             Tätigkeit (P106)
--   Bauwerk   Adresse (P6375 oder P669+P670, P281, P131), Koordinaten (P625),
--             Baudatum (P571), Architekt (P84), Baustil (P149)
--   Deckenbild Künstler (P170), Entstehung (P571), Technik (P186),
--             Maße (P2048 × P2049), Dargestellt (P180), Standort (P276/P361)
-- Ohne titel, bild und qid kein Popover.

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

-- ---------------------------------------------------------------------
-- Wikidata-Angaben im Popover, je nach Art der Entität
-- ---------------------------------------------------------------------

local ROLE_KIND = {
	Bauwerk = 'building', Raum = 'building',
	Auftraggeber = 'person', Maler = 'person', Stuckateur = 'person',
	Baumeister = 'person', Stecher = 'person', Kistler = 'person',
	Vergolder = 'person', Person = 'person',
	Deckenbild = 'painting',
}

local MONTHS = { 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
	'August', 'September', 'Oktober', 'November', 'Dezember' }

local UNITS = { Q174728 = 'cm', Q11573 = 'm', Q174789 = 'mm' }

local CIRCA = 'Q5727902'          -- P1480 »circa«
local MAX_VALUES = 3              -- Werte pro Eigenschaft
local MAX_LOOKUPS = 15            -- nachgeladene Bezeichnungen pro Popover

-- Bezeichnungen verknüpfter Items; jede braucht einen eigenen Abruf, daher
-- gedeckelt. Ohne Abruf (Erweiterung fehlt, Deckel erreicht, nicht im Cache)
-- erscheint die Q-Nummer.
local labelCache, lookups = {}, 0
local function itemLabel(qid)
	if labelCache[qid] then return labelCache[qid] end
	local label
	if lookups < MAX_LOOKUPS then
		lookups = lookups + 1
		local e = getEntity(qid)
		label = e and firstText(e.labels)
	end
	label = label or qid
	labelCache[qid] = label
	return label
end

-- Aussagen einer Eigenschaft nach Rang: bevorzugte, sonst normale.
local function bestStatements(entity, pid)
	local all = entity.claims and entity.claims[pid]
	if not all then return {} end
	local preferred, normal = {}, {}
	for _, st in ipairs(all) do
		if st.rank == 'preferred' then table.insert(preferred, st)
		elseif st.rank ~= 'deprecated' then table.insert(normal, st) end
	end
	return #preferred > 0 and preferred or normal
end

local function snakItemId(snak)
	local dv = snak and snak.snaktype == 'value' and snak.datavalue
	if dv and dv.type == 'wikibase-entityid' then
		return dv.value.id or ('Q' .. tostring(dv.value['numeric-id']))
	end
	return nil
end

local function hasQualifierItem(st, pid, qid)
	for _, q in ipairs((st.qualifiers and st.qualifiers[pid]) or {}) do
		if snakItemId(q) == qid then return true end
	end
	return false
end

local function formatTime(v)
	local sign, y, m, d = (v.time or ''):match('^([+-])(%d+)-(%d%d)-(%d%d)')
	if not y then return nil end
	y, m, d = tonumber(y), tonumber(m), tonumber(d)
	local prec = v.precision or 11
	local s
	if prec >= 11 and m > 0 and d > 0 then
		s = d .. '. ' .. MONTHS[m] .. ' ' .. y
	elseif prec == 10 and m > 0 then
		s = MONTHS[m] .. ' ' .. y
	elseif prec == 8 then
		s = (math.floor(y / 10) * 10) .. 'er Jahre'
	elseif prec <= 7 then
		s = (math.floor((y - 1) / 100) + 1) .. '. Jahrhundert'
	else
		s = tostring(y)
	end
	if sign == '-' then s = s .. ' v. Chr.' end
	return s
end

local function yearOf(v)
	local y = (v and v.time or ''):match('^[+-](%d+)')
	return y and tostring(tonumber(y)) or nil
end

local function formatCoord(v)
	local lat, lon = tonumber(v.latitude), tonumber(v.longitude)
	if not lat or not lon then return nil end
	local function part(x, pos, neg)
		return (string.format('%.4f', math.abs(x)):gsub('%.', ',')) .. '° ' .. (x < 0 and neg or pos)
	end
	return string.format('[https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f#map=17/%.6f/%.6f %s, %s]',
		lat, lon, lat, lon, part(lat, 'N', 'S'), part(lon, 'O', 'W'))
end

local function formatQuantity(v)
	local amount = tonumber(v.amount)
	if not amount then return nil end
	local s = (tostring(amount):gsub('%.0$', ''):gsub('%.', ','))
	local unitId = (v.unit or ''):match('(Q%d+)$')
	if unitId then s = s .. ' ' .. (UNITS[unitId] or itemLabel(unitId)) end
	return s
end

-- Wert eines Snaks als Wikitext, oder nil.
local function formatSnak(snak)
	if not snak then return nil end
	if snak.snaktype == 'somevalue' then return 'unbekannt' end
	local dv = snak.snaktype == 'value' and snak.datavalue
	if not dv then return nil end
	local t, v = dv.type, dv.value
	if t == 'wikibase-entityid' then return mw.text.nowiki(itemLabel(snakItemId(snak)))
	elseif t == 'time' then return formatTime(v)
	elseif t == 'globecoordinate' then return formatCoord(v)
	elseif t == 'quantity' then return formatQuantity(v)
	elseif t == 'monolingualtext' then return mw.text.nowiki(v.text)
	elseif t == 'string' then return mw.text.nowiki(v)
	end
	return nil
end

-- Hauptwert einer Aussage, mit »um« (P1480 circa) und Zeitraum aus den
-- Qualifikatoren P580/P582, falls vorhanden.
local function formatStatement(st, withPeriod)
	local s = formatSnak(st.mainsnak)
	if not s then return nil end
	if hasQualifierItem(st, 'P1480', CIRCA) then s = 'um ' .. s end
	if withPeriod and st.qualifiers then
		local q = st.qualifiers
		local from = q.P580 and q.P580[1] and q.P580[1].datavalue and yearOf(q.P580[1].datavalue.value)
		local to = q.P582 and q.P582[1] and q.P582[1].datavalue and yearOf(q.P582[1].datavalue.value)
		if from or to then s = s .. ' (' .. (from or '') .. '–' .. (to or '') .. ')' end
	end
	return s
end

-- Alle Werte einer Eigenschaft, durch Komma getrennt.
local function values(entity, pid, withPeriod)
	local out = {}
	for _, st in ipairs(bestStatements(entity, pid)) do
		local s = formatStatement(st, withPeriod)
		if s then table.insert(out, s) end
		if #out >= MAX_VALUES then break end
	end
	return #out > 0 and table.concat(out, ', ') or nil
end

local function first(entity, pid)
	return formatStatement(bestStatements(entity, pid)[1] or {}) or nil
end

-- Datum und Ort zusammen: »12. Mai 1700, München«
local function dateAndPlace(entity, datePid, placePid)
	local parts = {}
	local d, pl = first(entity, datePid), first(entity, placePid)
	if d then table.insert(parts, d) end
	if pl then table.insert(parts, pl) end
	return #parts > 0 and table.concat(parts, ', ') or nil
end

local function address(entity)
	local street = first(entity, 'P6375')
	if not street then
		local st = bestStatements(entity, 'P669')[1]
		street = st and formatSnak(st.mainsnak)
		if street then
			local nr = st.qualifiers and st.qualifiers.P670 and formatSnak(st.qualifiers.P670[1])
			if nr then street = street .. ' ' .. nr end
		end
	end
	if not street then return nil end
	local place = first(entity, 'P131')
	local zip = first(entity, 'P281')
	if place and zip then place = zip .. ' ' .. place end
	-- P6375 enthält oft schon den Ort
	if place and not street:find(first(entity, 'P131'), 1, true) then
		return street .. ', ' .. place
	end
	return street
end

local function dimensions(entity)
	local h, w = first(entity, 'P2048'), first(entity, 'P2049')
	if h and w then
		local hn, hu = h:match('^(%S+) (.+)$')
		local wn, wu = w:match('^(%S+) (.+)$')
		if hu and hu == wu then return hn .. ' × ' .. wn .. ' ' .. hu end
		return h .. ' × ' .. w
	end
	return h or w
end

-- Je Art: Liste von { Beschriftung, Funktion(entity) -> Wikitext|nil }
local FACTS = {
	person = {
		{ 'Geboren', function(e) return dateAndPlace(e, 'P569', 'P19') end },
		{ 'Gestorben', function(e) return dateAndPlace(e, 'P570', 'P20') end },
		{ 'Wirkungsort', function(e) return values(e, 'P937', true) end },
		{ 'Tätigkeit', function(e) return values(e, 'P106') end },
	},
	building = {
		{ 'Adresse', address },
		{ 'Ort', function(e)
			if first(e, 'P6375') or first(e, 'P669') then return nil end
			return first(e, 'P131')
		end },
		{ 'Koordinaten', function(e) return first(e, 'P625') end },
		{ 'Erbaut', function(e) return values(e, 'P571', true) end },
		{ 'Architekt', function(e) return values(e, 'P84') end },
		{ 'Baustil', function(e) return values(e, 'P149') end },
	},
	painting = {
		{ 'Künstler', function(e) return values(e, 'P170') end },
		{ 'Entstanden', function(e) return values(e, 'P571') end },
		{ 'Technik', function(e) return values(e, 'P186') end },
		{ 'Maße', dimensions },
		{ 'Dargestellt', function(e) return values(e, 'P180') end },
		{ 'Standort', function(e) return values(e, 'P276') or values(e, 'P361') end },
	},
}

local function entityKind(rolle, entity)
	local kind = rolle and ROLE_KIND[rolle]
	if kind then return kind end
	for _, st in ipairs(bestStatements(entity, 'P31')) do
		if snakItemId(st.mainsnak) == 'Q5' then return 'person' end
	end
	return nil
end

local function factRows(kind, entity)
	local spec = kind and FACTS[kind]
	if not spec then return nil end
	local rows = {}
	for _, f in ipairs(spec) do
		local ok, v = pcall(f[2], entity)
		if ok and v then
			table.insert(rows, '<span class="ent-fact"><span class="ent-key">' .. f[1] ..
				'</span> ' .. v .. '</span>')
		end
	end
	return #rows > 0 and table.concat(rows) or nil
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
	local facts = entity and factRows(entityKind(rolle, entity), entity)
	if facts then
		table.insert(rows, '<span class="ent-facts">' .. facts .. '</span>')
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
