import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, ScanSearch, Plus, Trash2, Link2, RefreshCw } from 'lucide-react';
import { useToast } from "@/hooks/use-toast";
import { v4 as uuidv4 } from 'uuid'; // Importiere UUID

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

interface Concept {
  id: string;
  text: string;
  x: number;
  y: number;
  isMainTopic?: boolean;
}

interface Connection {
  id: string;
  sourceId: string;
  targetId: string;
  label: string;
}

const findFreePosition = (existingConcepts: Concept[], containerWidth: number, containerHeight: number, centerX: number, centerY: number, isMainTopic: boolean = false): { x: number, y: number } => {
  const cardWidth = 100;
  const cardHeight = 40;
  const minDistanceX = 180;
  const minDistanceY = 100;
  const maxAttempts = 100;

  const mainRadius = 250;
  const secondaryRadius = 400;

  if (isMainTopic) {
    return { x: centerX, y: centerY };
  }

  const isDirectSubtopic = existingConcepts.length <= 10;
  const radius = isDirectSubtopic ? mainRadius : secondaryRadius;

  if (isDirectSubtopic) {
    const mainTopicIndex = existingConcepts.findIndex(c => c.isMainTopic);
    const subtopicCount = existingConcepts.length - (mainTopicIndex >= 0 ? 1 : 0);
    
    const angleStep = (2 * Math.PI) / Math.max(subtopicCount, 1);
    const index = existingConcepts.length - (mainTopicIndex >= 0 ? 1 : 0);
    const angle = index * angleStep;
    
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    
    return { x, y };
  }

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const angle = Math.random() * 2 * Math.PI;
    const randomRadius = radius * (0.8 + Math.random() * 0.4);
    const x = centerX + randomRadius * Math.cos(angle);
    const y = centerY + randomRadius * Math.sin(angle);

    const isFree = existingConcepts.every(concept => {
      const dx = Math.abs(concept.x - x);
      const dy = Math.abs(concept.y - y);
      return dx >= minDistanceX || dy >= minDistanceY;
    });

    if (isFree) {
      return { x, y };
    }
  }

  const wideRadius = secondaryRadius * 1.2;
  const angle = Math.random() * 2 * Math.PI;
  return {
    x: centerX + wideRadius * Math.cos(angle),
    y: centerY + wideRadius * Math.sin(angle),
  };
};

const calculatePositionRelativeToParent = (
  parentConcept: Concept,
  existingConcepts: Concept[],
  containerWidth: number,
  containerHeight: number,
  centerX: number,
  centerY: number,
  connections: Connection[]
): { x: number, y: number } => {
  // Finde bereits mit dem Elternkonzept verbundene Konzepte
  const connectedToParent = existingConcepts.filter(c => 
    connections.some(conn => 
      (conn.sourceId === parentConcept.id && conn.targetId === c.id) || 
      (conn.targetId === parentConcept.id && conn.sourceId === c.id)
    )
  );
  
  // Finde das Hauptthema
  const mainTopic = existingConcepts.find(c => c.isMainTopic);
  
  const parentX = parentConcept.x;
  const parentY = parentConcept.y;
  
  // Berechne den Winkel vom Eltern-Topic zum Hauptthema
  let angleToMain = 0;
  if (mainTopic) {
    angleToMain = Math.atan2(mainTopic.y - parentY, mainTopic.x - parentX);
  }
  
  // Parameter für Positionierung
  const DISTANCE_FROM_PARENT = 400; // Deutlich erhöhter Abstand zum Eltern-Topic
  const PARENT_ZONE_RADIUS = 150; // Radius der "verbotenen Zone" um das Eltern-Topic
  
  // Anzahl der bereits vorhandenen Kinder + das neue Kind
  const childCount = connectedToParent.length + 1;
  
  // Index des aktuellen Kindes
  const childIndex = connectedToParent.length;
  
  // Definiere den "verbotenen Sektor": ±60 Grad in Richtung des Hauptthemas
  const FORBIDDEN_ANGLE_RANGE = Math.PI / 3; // 60 Grad
  
  // Berechne einen Kreiswinkel basierend auf dem Index
  // Der Gesamtwinkelbereich ist jetzt 360° - 60° = 300° (wegen des verbotenen Sektors)
  // Wir starten mit einem Offset, um den verbotenen Sektor zu vermeiden
  const TOTAL_ANGLE_RANGE = 2 * Math.PI - FORBIDDEN_ANGLE_RANGE;
  
  // Berechne einen Basiswinkel für dieses Kind
  let baseAngle = (childIndex * TOTAL_ANGLE_RANGE) / Math.max(childCount, 4);
  
  // Füge Offset hinzu, um den verbotenen Sektor zu umgehen
  let angle = baseAngle + angleToMain + FORBIDDEN_ANGLE_RANGE / 2;
  
  // Stelle sicher, dass der Winkel zwischen 0 und 2π liegt
  angle = angle % (2 * Math.PI);
  
  // Berechne die Position im Kreis um das Eltern-Topic mit erhöhtem Abstand
  let x = parentX + DISTANCE_FROM_PARENT * Math.cos(angle);
  let y = parentY + DISTANCE_FROM_PARENT * Math.sin(angle);
  
  // Stelle sicher, dass die Position innerhalb des Containers liegt
  const padding = 50;
  x = Math.max(padding, Math.min(containerWidth - padding, x));
  y = Math.max(padding, Math.min(containerHeight - padding, y));
  
  // Überprüfe auf Überlappungen mit bereits vorhandenen Konzepten
  // und deren "verbotenen Zonen"
  const minDistanceToOtherNodes = 150; // Erhöhter Mindestabstand zu anderen Knoten
  
  // Versuche bis zu 5 mal, eine nicht überlappende Position zu finden
  for (let attempt = 0; attempt < 5; attempt++) {
    let hasOverlap = false;
    
    // Prüfe Überlappungen mit anderen Konzepten
    hasOverlap = existingConcepts.some(concept => {
      if (concept.id === parentConcept.id) return false;
      
      const dx = Math.abs(concept.x - x);
      const dy = Math.abs(concept.y - y);
      const distance = Math.sqrt(dx * dx + dy * dy);
      
      // Überprüfe, ob das neue Konzept in der verbotenen Zone eines Konzepts liegt
      // Für Elternkonzepte verwenden wir einen grösseren Radius (PARENT_ZONE_RADIUS)
      // Für andere Konzepte verwenden wir minDistanceToOtherNodes
      const conceptZoneRadius = connections.some(conn => 
        (conn.sourceId === concept.id || conn.targetId === concept.id) && 
        (conn.sourceId === mainTopic?.id || conn.targetId === mainTopic?.id)
      ) ? PARENT_ZONE_RADIUS : minDistanceToOtherNodes;
      
      return distance < conceptZoneRadius;
    });
    
    if (!hasOverlap) break;
    
    // Erhöhe den Abstand bei Überlappung, aber behalte die Richtung bei
    const newDistance = DISTANCE_FROM_PARENT + (attempt + 1) * 70; // Noch grössere Schritte
    x = parentX + newDistance * Math.cos(angle);
    y = parentY + newDistance * Math.sin(angle);
    
    // Stelle sicher, dass die Position innerhalb des Containers liegt
    x = Math.max(padding, Math.min(containerWidth - padding, x));
    y = Math.max(padding, Math.min(containerHeight - padding, y));
  }
  
  return { x, y };
};

// Funktion zur Generierung eindeutiger IDs mit UUID
const generateUniqueId = () => uuidv4();

const ConceptMapper = ({ sessionId: propsSessionId }: { sessionId?: string }) => {
  const { toast } = useToast();
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCreatingConnection, setIsCreatingConnection] = useState(false);
  const [connectionStart, setConnectionStart] = useState<string | null>(null);
  const [draggedConcept, setDraggedConcept] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [newConceptText, setNewConceptText] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [isEditingConnection, setIsEditingConnection] = useState<string | null>(null);
  const [connectionLabel, setConnectionLabel] = useState("");
  const [selectedConnection, setSelectedConnection] = useState<string | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>(propsSessionId);
  // Status für fehlende Credits und benötigte Credits-Anzeige
  const [creditsError, setCreditsError] = useState<{required: number, message: string} | null>(null);

  // Funktion, um die aktuelle Session-ID zu erhalten (aus Props oder localStorage)
  const getSessionId = (): string | undefined => {
    // Verwende die explizit übergebene Session-ID, wenn vorhanden
    if (currentSessionId) {
      return currentSessionId;
    }
    
    // Andernfalls versuche, sie aus dem localStorage zu holen
    const storedSessionId = localStorage.getItem('current_session_id');
    
    if (storedSessionId) {
      console.log('DEBUG: Using stored session ID from localStorage:', storedSessionId);
      // Aktualisiere den State, damit wir sie bei zukünftigen Aufrufen verwenden können
      setCurrentSessionId(storedSessionId);
      return storedSessionId;
    }
    
    return undefined;
  };
  
  useEffect(() => {
    // Update currentSessionId when propsSessionId changes
    if (propsSessionId && propsSessionId !== currentSessionId) {
      setCurrentSessionId(propsSessionId);
    }
  }, [propsSessionId]);

  useEffect(() => {
    const sessionId = getSessionId();
    if (sessionId) {
      // Prüfe ob wir gerade einen Reset durchgeführt haben
      const forceNewSession = sessionStorage.getItem('force_new_session');
      
      if (forceNewSession === 'true') {
        // Wenn wir gerade einen Reset durchgeführt haben, ignoriere die alte sessionId
        console.log('DEBUG: ConceptMapper - Ignoring old sessionId after reset');
        return;
      }
      
      fetchInitialConcepts(sessionId);
    }
  }, [currentSessionId]);

  const fetchInitialConcepts = async (sessionId: string) => {
    // Prüfe nochmals, ob wir in einem Reset-Zustand sind
    const forceNewSession = sessionStorage.getItem('force_new_session');
    if (forceNewSession === 'true') {
      console.log('DEBUG: ConceptMapper - fetchInitialConcepts canceled due to reset state');
      return;
    }
    
    try {
      // Get the token from localStorage
      const token = localStorage.getItem('exammaster_token');
      
      // First, try to get the topics with their IDs from the backend
      const topicsResponse = await fetch(`${API_URL}/api/v1/topics/${sessionId}`, {
        headers: {
          'Authorization': token ? `Bearer ${token}` : ''
        }
      });
      const topicsData = await topicsResponse.json();
      
      if (topicsData.success && topicsData.topics?.main_topic) {
        // If topics are available, use them
        const containerWidth = 1200;
        const containerHeight = 900;
        const centerX = containerWidth / 2;
        const centerY = containerHeight / 2;
        
        const mainTopic = topicsData.topics.main_topic;
        const subtopics = topicsData.topics.subtopics || [];
        const backendConnections = topicsData.connections || [];
        
        // Deduplizieren der Subtopics, um Wiederholungen zu vermeiden
        const uniqueSubtopics = [];
        const seenSubtopicNames = new Set();
        
        for (const subtopic of subtopics) {
          if (!seenSubtopicNames.has(subtopic.name)) {
            uniqueSubtopics.push(subtopic);
            seenSubtopicNames.add(subtopic.name);
          }
        }
        
        // Alle Subtopics verwenden, ohne Begrenzung
        const allSubtopics = uniqueSubtopics;
        
        // Create concepts from topics
        const mainConcept: Concept = {
          id: mainTopic.id.toString(),
          text: mainTopic.name,
          x: centerX,
          y: centerY,
          isMainTopic: true,
        };
        
        const subtopicConcepts: Concept[] = [];
        const radius = 250;
        const subtopicCount = allSubtopics.length;
        
        allSubtopics.forEach((topic, index) => {
          const angle = (index * 2 * Math.PI) / subtopicCount;
          const x = centerX + radius * Math.cos(angle);
          const y = centerY + radius * Math.sin(angle);
          
          subtopicConcepts.push({
            id: topic.id.toString(),
            text: topic.name,
            x,
            y,
          });
        });
        
        // Create connections from backend connections
        const frontendConnections: Connection[] = backendConnections.map(conn => ({
          id: conn.id.toString(),
          sourceId: conn.source_id.toString(),
          targetId: conn.target_id.toString(),
          label: conn.label || "verbunden mit" // Stelle sicher, dass es immer ein Label gibt
        }));
        
        // Setze Konzepte und Verbindungen
        // Jetzt nur das Hauptkonzept und die direkten Unterkonzepte laden 
        // (ohne childConcepts)
        setConcepts([mainConcept, ...subtopicConcepts]);
        setConnections(frontendConnections);
        
        // Setze loading auf false
        setIsGenerating(false);
      } else {
        // Wenn keine Topics verfügbar sind, erstelle ein leeres Hauptthema
        toast({
          title: "Keine Themen gefunden",
          description: "Es wurden keine Themen gefunden. Sie können ein neues Hauptthema hinzufügen.",
          variant: "default",
        });
        
        // Create empty main topic
        const containerWidth = 1200;
        const containerHeight = 900;
        const centerX = containerWidth / 2;
        const centerY = containerHeight / 2;
        
        setConcepts([{
          id: generateUniqueId(),
          text: "Hauptthema",
          x: centerX,
          y: centerY,
          isMainTopic: true,
        }]);
      }
    } catch (error) {
      console.error("Error fetching topics:", error);
      toast({
        title: "Fehler beim Laden der Themen",
        description: "Es ist ein Fehler beim Laden der Themen aufgetreten. Bitte versuchen Sie es später erneut.",
        variant: "destructive",
      });
    }
  };

  const generateConnectionsWithAI = async (existingConcepts, sessionId) => {
    const effectiveSessionId = sessionId || getSessionId();
    if (!effectiveSessionId) {
      toast({
        title: "Fehler",
        description: "Keine Sitzung vorhanden. Bitte lade zuerst eine Datei hoch.",
        variant: "destructive",
      });
      return;
    }
  
    try {
      setIsGenerating(true);
      
      // Define constants for positioning
      const containerWidth = 1200;
      const containerHeight = 900;
      const centerX = containerWidth / 2;
      const centerY = containerHeight / 2;
      
      // Get the token from localStorage
      const token = localStorage.getItem('exammaster_token');
      console.log("Token verfügbar:", !!token);
      
      // First, check if we have backend IDs for the topics
      const topicsResponse = await fetch(`${API_URL}/api/v1/topics/${effectiveSessionId}`, {
        headers: {
          'Authorization': token ? `Bearer ${token}` : ''
        }
      });
      const topicsData = await topicsResponse.json();
      console.log("Topics-API-Antwort:", topicsData);
      
      // If we don't have backend IDs yet, we need to generate related topics first
      // to create the topics in the backend
      if (!topicsData.success || !topicsData.topics?.main_topic) {
        toast({
          title: "Initialisiere Topics",
          description: "Die Topics werden zuerst im Backend initialisiert...",
        });
        
        // Wait a moment to allow the backend to process the upload
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Try again
        const retryResponse = await fetch(`${API_URL}/api/v1/topics/${effectiveSessionId}`, {
          headers: {
            'Authorization': token ? `Bearer ${token}` : ''
          }
        });
        const retryData = await retryResponse.json();
        console.log("Retry Topics-API-Antwort:", retryData);
        
        if (!retryData.success || !retryData.topics?.main_topic) {
          throw new Error("Topics konnten nicht initialisiert werden. Bitte lade die Seite neu.");
        }
      }
      
      // Stelle sicher, dass wir das Hauptthema und Subtopics haben
      if (!topicsData.topics?.main_topic || !topicsData.topics?.subtopics) {
        throw new Error("Keine Topics gefunden. Bitte lade die Seite neu.");
      }
      
      // Hole die aktuelle Konfiguration der Konzeptkarte
      const mainTopic = topicsData.topics.main_topic;
      const subtopics = topicsData.topics.subtopics;
      
      // Deduplizieren der Subtopics, um Wiederholungen zu vermeiden
      const uniqueSubtopics = [];
      const seenSubtopicNames = new Set();
      
      for (const subtopic of subtopics) {
        if (!seenSubtopicNames.has(subtopic.name)) {
          uniqueSubtopics.push(subtopic);
          seenSubtopicNames.add(subtopic.name);
        }
      }
      
      // Alle Subtopics verwenden, ohne Begrenzung
      const allSubtopics = uniqueSubtopics;
      
      console.log("Hauptthema:", mainTopic);
      console.log("Subtopics nach Deduplizierung:", allSubtopics);
      
      // Create a mapping from topic name to position
      const positionMap = {};
      existingConcepts.forEach(concept => {
        positionMap[concept.text] = { x: concept.x, y: concept.y };
      });
      
      // Sammle alle Konzepte und Verbindungen
      let allNewConcepts = [];
      let allNewConnections = [];
      
      // Hauptthema hinzufügen
      const mainConceptObj = {
        id: mainTopic.id.toString(),
        text: mainTopic.name,
        x: positionMap[mainTopic.name]?.x || centerX,
        y: positionMap[mainTopic.name]?.y || centerY,
        isMainTopic: true
      };
      allNewConcepts.push(mainConceptObj);
      
      // Subtopics hinzufügen
      const subtopicObjects = allSubtopics.map((subtopic, index) => {
        const angle = (index * 2 * Math.PI) / allSubtopics.length;
        const radius = 250;
        const x = positionMap[subtopic.name]?.x || (centerX + radius * Math.cos(angle));
        const y = positionMap[subtopic.name]?.y || (centerY + radius * Math.sin(angle));
        
        const subtopicObj = {
          id: subtopic.id.toString(),
          text: subtopic.name,
          x: x,
          y: y
        };
        
        // Verbindung zum Hauptthema
        allNewConnections.push({
          id: generateUniqueId(),
          sourceId: mainTopic.id.toString(),
          targetId: subtopic.id.toString(),
          label: `${mainTopic.name} enthält ${subtopic.name}`
        });
        
        return subtopicObj;
      });
      
      allNewConcepts.push(...subtopicObjects);
      console.log("Subtopics hinzugefügt:", subtopicObjects);
      
      // Für jedes Subtopic (Eltern-Topic) generiere Kinder-Topics
      for (const subtopic of allSubtopics) {
        console.log("Verarbeite Subtopic:", subtopic);
        
        // Prüfe, ob bereits Kind-Topics für dieses Subtopic existieren
        const existingChildTopics = allNewConcepts.filter(concept => 
          allNewConnections.some(conn => 
            conn.sourceId === subtopic.id.toString() && 
            conn.targetId === concept.id
          )
        );
        
        console.log("Existierende Kind-Topics für", subtopic.name, ":", existingChildTopics);

        // Falls bereits Kind-Topics existieren, überspringen
        if (existingChildTopics.length > 0) {
          console.log("Überspringe Subtopic, da bereits Kind-Topics existieren:", subtopic.name);
          continue;
        }

        // Generiere Kinder-Topics für dieses Subtopic
        console.log("Rufe API für Subtopic auf:", subtopic.name);
        console.log(`API-Anfrage an ${API_URL}/api/v1/generate-concept-map-suggestions mit sessionId: ${effectiveSessionId}`);
        console.log("Request Body:", {
          session_id: effectiveSessionId,
          parent_subtopics: [subtopic.name]
        });
        
        // Prüfe, ob sessionId und parentConcept vorhanden sind
        if (!effectiveSessionId) {
          toast({
            title: "Fehler",
            description: "Keine Session ID vorhanden. Bitte laden Sie zuerst eine Datei hoch.",
            variant: "destructive",
          });
          setIsGenerating(false);
          return;
        }
        
        if (!subtopic || !subtopic.text) {
          toast({
            title: "Fehler",
            description: "Kein gültiges Eltern-Konzept ausgewählt.",
            variant: "destructive",
          });
          setIsGenerating(false);
          return;
        }
        
        const response = await fetch(`${API_URL}/api/v1/generate-concept-map-suggestions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            session_id: effectiveSessionId,
            parent_subtopics: [subtopic.name]
          })
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error("API request failed:", response.status, errorText);
          
          // Spezielle Behandlung für 402 Payment Required (nicht genügend Credits)
          if (response.status === 402) {
            // Versuche, die Credits-Informationen aus der Fehlermeldung zu extrahieren
            let creditsRequired = 0;
            const creditsMatch = errorText.match(/Benötigt: (\d+) Credits/);
            if (creditsMatch && creditsMatch[1]) {
              creditsRequired = parseInt(creditsMatch[1], 10);
            }
            
            toast({
              title: "Nicht genügend Credits",
              description: `Du benötigst ${creditsRequired} Credits für diese Aktion. Bitte lade deine Credits auf.`,
              variant: "destructive",
              duration: 8000,
            });
            
            // Setze den Credits-Fehlerstatus statt eines window.confirm-Dialogs
            setCreditsError({
              required: creditsRequired,
              message: `Nicht genügend Credits. Benötigt: ${creditsRequired} Credits für diese Aktion.`
            });
            
            setIsGenerating(false);
            throw new Error(`Nicht genügend Credits. Benötigt: ${creditsRequired} Credits.`);
          }
          
          throw new Error(`API-Anfrage fehlgeschlagen: ${response.status} ${errorText}`);
        }
        
        const data = await response.json();
        console.log("API-Antwort:", data);
        
        if (data.success && data.data.suggestions) {
          const suggestions = data.data.suggestions;
          
          // Prüfen, ob der Eltern-Topic-Name im suggestions-Objekt existiert
          if (!suggestions[subtopic.name]) {
            console.error("Keine Vorschläge für das Eltern-Topic gefunden:", subtopic.name);
            console.log("Verfügbare Schlüssel in suggestions:", Object.keys(suggestions));
            
            // Versuche den ersten verfügbaren Schlüssel zu verwenden, falls vorhanden
            const firstKey = Object.keys(suggestions).find(key => 
              !key.endsWith('_relationships') && Array.isArray(suggestions[key])
            );
            
            if (firstKey) {
              console.log("Verwende alternativen Schlüssel:", firstKey);
              var childTopics = suggestions[firstKey] || [];
            } else {
              throw new Error(`Keine Vorschläge gefunden für "${subtopic.name}"`);
            }
          } else {
            var childTopics = suggestions[subtopic.name] || [];
          }
          
          console.log("Kind-Topics aus API:", childTopics);
          
          // Die Beziehungslabels vom Backend holen
          const relationshipKey = `${subtopic.name}_relationships`;
          const relationshipLabels = suggestions[relationshipKey] || {};
          
          // Fallback: Wenn keine Beziehungslabels für den genauen Schlüssel gefunden werden,
          // versuche den ersten verfügbaren *_relationships-Schlüssel
          let usedRelationshipLabels = relationshipLabels;
          if (Object.keys(relationshipLabels).length === 0) {
            const firstRelKey = Object.keys(suggestions).find(key => key.endsWith('_relationships'));
            if (firstRelKey) {
              console.log("Verwende alternativen Relationship-Key:", firstRelKey);
              usedRelationshipLabels = suggestions[firstRelKey] || {};
            }
          }
          
          console.log("Beziehungslabels aus API:", usedRelationshipLabels);
          
          // Container-Dimensionen
          const containerWidth = 1200;
          const containerHeight = 900;
          const centerX = containerWidth / 2;
          const centerY = containerHeight / 2;
          
          // Überprüfe auf Fehler im Fallback-Mechanismus (entfernen)
          if (childTopics.length === 0) {
            toast({
              title: "Keine Vorschläge verfügbar",
              description: `Es konnten keine Vorschläge für "${subtopic.name}" generiert werden.`,
              variant: "destructive",
            });
            setIsGenerating(false);
            return;
          }
          
          // Handle cases where childTopics might not be an array (entfernen des Fallbacks)
          if (!Array.isArray(childTopics)) {
            console.error("childTopics ist kein Array:", childTopics);
            toast({
              title: "Fehler beim Generieren",
              description: "Die API hat ein ungültiges Format zurückgegeben.",
              variant: "destructive",
            });
            setIsGenerating(false);
            return;
          }
          
          // Prüfe, ob wir weitere Kindthemen haben
          if (existingChildTopics.length < childTopics.length) {
            // Wähle das nächste Kind-Topic aus der Liste basierend auf der Anzahl der bereits existierenden
            const childTopic = childTopics[existingChildTopics.length];
            
            console.log("Ausgewähltes Kind-Topic:", childTopic);
            
            // Wenn childTopic ein Objekt ist, extrahiere den topic-Wert
            let childTopicText;
            if (typeof childTopic === 'object' && childTopic !== null && 'topic' in childTopic) {
              childTopicText = childTopic.topic;
            } else {
              childTopicText = childTopic;
            }
            
            // Zusätzliche Validierung: Prüfe, ob das ausgewählte Kind-Topic existiert
            if (!childTopicText) {
              console.error("Kind-Topic nicht gefunden für Index:", existingChildTopics.length);
              // Erstelle ein Dummy-Topic - nur ein einzelnes Kind pro Klick
              childTopicText = `${subtopic.name} Component ${existingChildTopics.length + 1}`;
              console.log("Erstelltes Dummy-Topic:", childTopicText);
            }
            
            // Neue Konzepte erstellen
            let newConcepts = [...concepts];
            let newConnections = [...connections];
            
            const childId = generateUniqueId();
            
            // Position relativ zum Elternkonzept berechnen
            const position = calculatePositionRelativeToParent(
              subtopicObjects.find(c => c.id === subtopic.id.toString()),
              newConcepts,
              containerWidth,
              containerHeight,
              centerX,
              centerY,
              newConnections
            );
            
            console.log("Berechnete Position für Kind-Topic:", position);
            
            // Neues Kind-Topic hinzufügen
            const childConceptObj = {
              id: childId,
              text: childTopicText,
              x: position.x,
              y: position.y
            };
            
            console.log("Neues Kind-Topic-Objekt:", childConceptObj);
            
            newConcepts.push(childConceptObj);
            
            // Verbindungslabel aus den Beziehungslabels holen oder Fallback verwenden
            let connectionLabel;
            
            // Wenn childTopic ein Objekt ist mit relationship-Feld, verwende dieses
            if (typeof childTopic === 'object' && childTopic !== null && 'relationship' in childTopic) {
              connectionLabel = childTopic.relationship;
            } else {
              // Sonst versuche in relationshipLabels zu finden oder verwende Fallback
              connectionLabel = usedRelationshipLabels[childTopicText] || `${subtopic.name} umfasst ${childTopicText}`;
            }
            
            // Verbindung mit Label erstellen
            const newConnection = {
              id: generateUniqueId(),
              sourceId: subtopic.id.toString(),
              targetId: childId,
              label: connectionLabel
            };
            
            console.log("Neue Verbindung:", newConnection);
            
            newConnections.push(newConnection);
            
            // Vor dem Update der States
            console.log("Vorher - Anzahl der Concepts:", concepts.length);
            console.log("Vorher - Anzahl der Connections:", connections.length);
            
            // Update state
            setConcepts(newConcepts);
            setConnections(newConnections);
            
            // Nach dem Update der States verzögerte Überprüfung
            setTimeout(() => {
              console.log("Nachher - Anzahl der Concepts:", concepts.length);
              console.log("Nachher - Anzahl der Connections:", connections.length);
              console.log("Alle Concepts nach Update:", concepts);
              console.log("Alle Connections nach Update:", connections);
            }, 500);
            
            toast({
              title: "Vorschlag generiert",
              description: `Kind-Thema #${existingChildTopics.length + 1} für "${subtopic.name}" wurde hinzugefügt.`,
              variant: "default",
            });
          } else {
            toast({
              title: "Keine weiteren Vorschläge",
              description: `Alle verfügbaren Kind-Themen für "${subtopic.name}" wurden bereits hinzugefügt.`,
              variant: "default",
            });
          }
        } else {
          console.error("API-Antwort ungültig:", data);
          toast({
            title: "Fehler",
            description: "Fehler beim Generieren der Vorschläge: " + (data.message || "Ungültige Antwort"),
            variant: "destructive",
          });
        }
      }
      
      console.log("Alle neuen Concepts:", allNewConcepts);
      console.log("Alle neuen Verbindungen:", allNewConnections);
      
      // Vor dem Update der States
      console.log("Vorher - Anzahl der Concepts:", concepts.length);
      console.log("Vorher - Anzahl der Connections:", connections.length);
      
      // Aktualisiere das UI mit allen gesammelten Konzepten und Verbindungen
      setConcepts(allNewConcepts);
      setConnections(allNewConnections);
      
      // Nach dem Update der States verzögerte Überprüfung
      setTimeout(() => {
        console.log("Nachher - Anzahl der Concepts:", concepts.length);
        console.log("Nachher - Anzahl der Connections:", connections.length);
      }, 500);
      
      toast({
        title: "KI-Vorschläge generiert",
        description: "Für jedes Eltern-Topic wurden Kind-Topics generiert.",
      });
    } catch (error) {
      console.error("Fehler beim Generieren der Verbindungen:", error);
      toast({
        title: "Fehler",
        description: "Kind-Subtopics konnten nicht generiert werden: " + error.message,
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAddConcept = () => {
    if (!newConceptText.trim()) return;

    const containerWidth = 1200;
    const containerHeight = 900;
    const centerX = containerWidth / 2;
    const centerY = containerHeight / 2;
    const newId = generateUniqueId();
    
    const mainTopic = concepts.find(c => c.isMainTopic);
    
    let x, y;
    
    if (mainTopic) {
      const nonMainTopics = concepts.filter(c => !c.isMainTopic);
      const angle = ((nonMainTopics.length + 1) * 2 * Math.PI) / (nonMainTopics.length + 2);
      const radius = 250;
      
      x = centerX + radius * Math.cos(angle);
      y = centerY + radius * Math.sin(angle);
    } else {
      const position = findFreePosition(concepts, containerWidth, containerHeight, centerX, centerY);
      x = position.x;
      y = position.y;
    }

    setConcepts([...concepts, {
      id: newId,
      text: newConceptText,
      x,
      y,
    }]);
    
    if (mainTopic) {
      setConnections([...connections, {
        id: generateUniqueId(),
        sourceId: mainTopic.id,
        targetId: newId,
        label: ""
      }]);
    }

    setNewConceptText("");
    setShowAddForm(false);

    toast({
      title: "Konzept hinzugefügt",
      description: `"${newConceptText}" wurde zur Konzeptkarte hinzugefügt.`,
    });
  };

  const startDrag = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    if (!isCreatingConnection) {
      const concept = concepts.find(c => c.id === id);
      if (!concept) return;

      setDraggedConcept(id);
      setDragOffset({
        x: (e.clientX / zoomLevel) - concept.x,
        y: (e.clientY / zoomLevel) - concept.y
      });
    }
  };

  const handleDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    if (draggedConcept) {
      setConcepts(concepts.map(c => {
        if (c.id === draggedConcept) {
          return {
            ...c,
            x: (e.clientX / zoomLevel) - dragOffset.x,
            y: (e.clientY / zoomLevel) - dragOffset.y
          };
        }
        return c;
      }));
    }
  };

  const endDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    setDraggedConcept(null);
  };

  const startConnection = (id: string) => {
    if (isCreatingConnection) {
      if (id !== connectionStart && connectionStart) {
        const newId = generateUniqueId();
        setConnectionLabel("");
        setIsEditingConnection(newId);

        setConnections([...connections, {
          id: newId,
          sourceId: connectionStart,
          targetId: id,
          label: ""
        }]);
      }
      setIsCreatingConnection(false);
      setConnectionStart(null);
    } else {
      setIsCreatingConnection(true);
      setConnectionStart(id);
    }
  };

  const cancelConnection = () => {
    setIsCreatingConnection(false);
    setConnectionStart(null);
  };

  const deleteConcept = (id: string) => {
    setConcepts(concepts.filter(c => c.id !== id));
    setConnections(connections.filter(
      conn => conn.sourceId !== id && conn.targetId !== id
    ));
  };

  const deleteConnection = (id: string) => {
    setConnections(connections.filter(conn => conn.id !== id));
    setSelectedConnection(null);
    setIsEditingConnection(null);
  };

  const saveConnectionLabel = () => {
    if (!isEditingConnection) return;

    setConnections(connections.map(conn => {
      if (conn.id === isEditingConnection) {
        return { ...conn, label: connectionLabel };
      }
      return conn;
    }));

    setIsEditingConnection(null);
    setConnectionLabel("");
  };

  const cancelEditingLabel = () => {
    setIsEditingConnection(null);
    setConnectionLabel("");
  };

  const generateNewConcepts = async () => {
    if (!currentSessionId) {
      toast({
        title: "Fehler",
        description: "Keine Sitzung vorhanden. Bitte lade zuerst eine Datei hoch.",
        variant: "destructive",
      });
      return;
    }

    await generateConnectionsWithAI(concepts, currentSessionId);
  };

  const openConnectionPopup = (connectionId: string) => {
    setSelectedConnection(connectionId);
  };

  const closeConnectionPopup = () => {
    setSelectedConnection(null);
    setIsEditingConnection(null);
    setConnectionLabel("");
  };

  // Erweitere die generateChildSuggestions-Funktion, um Kindkonzepte zu laden und mit Labels zu versehen
  const generateChildSuggestions = async (parentId) => {
    setIsGenerating(true);
    
    try {
      const token = localStorage.getItem('exammaster_token');
      const parentConcept = concepts.find(c => c.id === parentId);
      const effectiveSessionId = getSessionId();
      
      if (!parentConcept) {
        toast({
          title: "Fehler",
          description: "Elternkonzept nicht gefunden.",
          variant: "destructive",
        });
        setIsGenerating(false);
        return;
      }
      
      // Finde alle bereits existierenden Kind-Topics für dieses Eltern-Topic
      const existingChildTopics = concepts.filter(concept => 
        connections.some(conn => 
          conn.sourceId === parentId && 
          conn.targetId === concept.id
        )
      );
      
      // Anzahl der bereits existierenden Kind-Topics für dieses Eltern-Topic
      const existingChildCount = existingChildTopics.length;
      
      console.log("Eltern-Topic:", parentConcept);
      console.log("Existierende Kind-Topics:", existingChildTopics);
      console.log("Existierende Kind-Topics Anzahl:", existingChildCount);
      
      // API-Aufruf zum Generieren von Vorschlägen
      console.log(`API-Anfrage an ${API_URL}/api/v1/generate-concept-map-suggestions mit sessionId: ${effectiveSessionId}`);
      console.log("Request Body:", {
        session_id: effectiveSessionId,
        parent_subtopics: [parentConcept.text]
      });
      
      // Prüfe, ob sessionId und parentConcept vorhanden sind
      if (!effectiveSessionId) {
        toast({
          title: "Fehler",
          description: "Keine Session ID vorhanden. Bitte laden Sie zuerst eine Datei hoch.",
          variant: "destructive",
        });
        setIsGenerating(false);
        return;
      }
      
      if (!parentConcept.text) {
        toast({
          title: "Fehler",
          description: "Kein gültiges Eltern-Konzept ausgewählt.",
          variant: "destructive",
        });
        setIsGenerating(false);
        return;
      }
      
      // Stellen Sie sicher, dass das Token vorhanden ist
      if (!token) {
        toast({
          title: "Nicht authentifiziert",
          description: "Bitte melden Sie sich an, um diese Funktion zu nutzen.",
          variant: "destructive",
        });
        setIsGenerating(false);
        return;
      }
      
      const response = await fetch(`${API_URL}/api/v1/generate-concept-map-suggestions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_id: effectiveSessionId,
          parent_subtopics: [parentConcept.text]
        })
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("API request failed:", response.status, errorText);
        
        // Spezielle Behandlung für 402 Payment Required (nicht genügend Credits)
        if (response.status === 402) {
          // Versuche, die Credits-Informationen aus der Fehlermeldung zu extrahieren
          let creditsRequired = 0;
          const creditsMatch = errorText.match(/Benötigt: (\d+) Credits/);
          if (creditsMatch && creditsMatch[1]) {
            creditsRequired = parseInt(creditsMatch[1], 10);
          }
          
          toast({
            title: "Nicht genügend Credits",
            description: `Du benötigst ${creditsRequired} Credits für diese Aktion. Bitte lade deine Credits auf.`,
            variant: "destructive",
            duration: 8000,
          });
          
          // Setze den Credits-Fehlerstatus statt eines window.confirm-Dialogs
          setCreditsError({
            required: creditsRequired,
            message: `Nicht genügend Credits. Benötigt: ${creditsRequired} Credits für diese Aktion.`
          });
          
          setIsGenerating(false);
          throw new Error(`Nicht genügend Credits. Benötigt: ${creditsRequired} Credits.`);
        }
        
        throw new Error(`API-Anfrage fehlgeschlagen: ${response.status} ${errorText}`);
      }
      
      const data = await response.json();
      console.log("API-Antwort:", data);
      
      if (data.success && data.data.suggestions) {
        const suggestions = data.data.suggestions;
        
        // Prüfen, ob der Eltern-Topic-Name im suggestions-Objekt existiert
        if (!suggestions[parentConcept.text]) {
          console.error("Keine Vorschläge für das Eltern-Topic gefunden:", parentConcept.text);
          console.log("Verfügbare Schlüssel in suggestions:", Object.keys(suggestions));
          
          // Versuche den ersten verfügbaren Schlüssel zu verwenden, falls vorhanden
          const firstKey = Object.keys(suggestions).find(key => 
            !key.endsWith('_relationships') && Array.isArray(suggestions[key])
          );
          
          if (firstKey) {
            console.log("Verwende alternativen Schlüssel:", firstKey);
            var childTopics = suggestions[firstKey] || [];
          } else {
            throw new Error(`Keine Vorschläge gefunden für "${parentConcept.text}"`);
          }
        } else {
          var childTopics = suggestions[parentConcept.text] || [];
        }
        
        console.log("Kind-Topics aus API:", childTopics);
        
        // Die Beziehungslabels vom Backend holen
        const relationshipKey = `${parentConcept.text}_relationships`;
        const relationshipLabels = suggestions[relationshipKey] || {};
        
        // Fallback: Wenn keine Beziehungslabels für den genauen Schlüssel gefunden werden,
        // versuche den ersten verfügbaren *_relationships-Schlüssel
        let usedRelationshipLabels = relationshipLabels;
        if (Object.keys(relationshipLabels).length === 0) {
          const firstRelKey = Object.keys(suggestions).find(key => key.endsWith('_relationships'));
          if (firstRelKey) {
            console.log("Verwende alternativen Relationship-Key:", firstRelKey);
            usedRelationshipLabels = suggestions[firstRelKey] || {};
          }
        }
        
        console.log("Beziehungslabels aus API:", usedRelationshipLabels);
        
        // Container-Dimensionen
        const containerWidth = 1200;
        const containerHeight = 900;
        const centerX = containerWidth / 2;
        const centerY = containerHeight / 2;
        
        // Überprüfe auf Fehler im Fallback-Mechanismus (entfernen)
        if (childTopics.length === 0) {
          toast({
            title: "Keine Vorschläge verfügbar",
            description: `Es konnten keine Vorschläge für "${parentConcept.text}" generiert werden.`,
            variant: "destructive",
          });
          setIsGenerating(false);
          return;
        }
        
        // Handle cases where childTopics might not be an array (entfernen des Fallbacks)
        if (!Array.isArray(childTopics)) {
          console.error("childTopics ist kein Array:", childTopics);
          toast({
            title: "Fehler beim Generieren",
            description: "Die API hat ein ungültiges Format zurückgegeben.",
            variant: "destructive",
          });
          setIsGenerating(false);
          return;
        }
        
        // Prüfe, ob wir weitere Kindthemen haben
        if (existingChildCount < childTopics.length) {
          // Wähle das nächste Kind-Topic aus der Liste basierend auf der Anzahl der bereits existierenden
          const childTopic = childTopics[existingChildCount];
          
          console.log("Ausgewähltes Kind-Topic:", childTopic);
          
          // Wenn childTopic ein Objekt ist, extrahiere den topic-Wert
          let childTopicText;
          if (typeof childTopic === 'object' && childTopic !== null && 'topic' in childTopic) {
            childTopicText = childTopic.topic;
          } else {
            childTopicText = childTopic;
          }
          
          // Zusätzliche Validierung: Prüfe, ob das ausgewählte Kind-Topic existiert
          if (!childTopicText) {
            console.error("Kind-Topic nicht gefunden für Index:", existingChildCount);
            // Erstelle ein Dummy-Topic - nur ein einzelnes Kind pro Klick
            childTopicText = `${parentConcept.text} Component ${existingChildCount + 1}`;
            console.log("Erstelltes Dummy-Topic:", childTopicText);
          }
          
          // Neue Konzepte erstellen
          let newConcepts = [...concepts];
          let newConnections = [...connections];
          
          const childId = generateUniqueId();
          
          // Position relativ zum Elternkonzept berechnen
          const position = calculatePositionRelativeToParent(
            parentConcept,
            newConcepts,
            containerWidth,
            containerHeight,
            centerX,
            centerY,
            newConnections
          );
          
          console.log("Berechnete Position für Kind-Topic:", position);
          
          // Neues Kind-Topic hinzufügen
          const childConceptObj = {
            id: childId,
            text: childTopicText,
            x: position.x,
            y: position.y
          };
          
          console.log("Neues Kind-Topic-Objekt:", childConceptObj);
          
          newConcepts.push(childConceptObj);
          
          // Verbindungslabel aus den Beziehungslabels holen oder Fallback verwenden
          let connectionLabel;
          
          // Wenn childTopic ein Objekt ist mit relationship-Feld, verwende dieses
          if (typeof childTopic === 'object' && childTopic !== null && 'relationship' in childTopic) {
            connectionLabel = childTopic.relationship;
          } else {
            // Sonst versuche in relationshipLabels zu finden oder verwende Fallback
            connectionLabel = usedRelationshipLabels[childTopicText] || `${parentConcept.text} umfasst ${childTopicText}`;
          }
          
          // Verbindung mit Label erstellen
          const newConnection = {
            id: generateUniqueId(),
            sourceId: parentId,
            targetId: childId,
            label: connectionLabel
          };
          
          console.log("Neue Verbindung:", newConnection);
          
          newConnections.push(newConnection);
          
          // Vor dem Update der States
          console.log("Vorher - Anzahl der Concepts:", concepts.length);
          console.log("Vorher - Anzahl der Connections:", connections.length);
          
          // Update state
          setConcepts(newConcepts);
          setConnections(newConnections);
          
          // Nach dem Update der States verzögerte Überprüfung
          setTimeout(() => {
            console.log("Nachher - Anzahl der Concepts:", concepts.length);
            console.log("Nachher - Anzahl der Connections:", connections.length);
            console.log("Alle Concepts nach Update:", concepts);
            console.log("Alle Connections nach Update:", connections);
          }, 500);
          
          toast({
            title: "Vorschlag generiert",
            description: `Kind-Thema #${existingChildCount + 1} für "${parentConcept.text}" wurde hinzugefügt.`,
            variant: "default",
          });
        } else {
          toast({
            title: "Keine weiteren Vorschläge",
            description: `Alle verfügbaren Kind-Themen für "${parentConcept.text}" wurden bereits hinzugefügt.`,
            variant: "default",
          });
        }
      } else {
        console.error("API-Antwort ungültig:", data);
        toast({
          title: "Fehler",
          description: "Fehler beim Generieren der Vorschläge: " + (data.message || "Ungültige Antwort"),
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Error generating suggestions:", error);
      toast({
        title: "Fehler",
        description: "Es ist ein Fehler beim Generieren der Vorschläge aufgetreten: " + error.message,
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <section id="concept-mapper" className="section-container bg-secondary/30">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12 space-y-4">
          <h2 className="text-3xl md:text-4xl font-bold animate-fade-in">
            Interaktives Konzeptmapping
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto animate-fade-in">
            Visualisiere Zusammenhänge und erstelle Wissensnetze zu deinen Prüfungsthemen.
          </p>
        </div>

        <div className="mb-4 flex flex-wrap gap-2 justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowAddForm(!showAddForm)}
            className="gap-1"
          >
            <Plus className="h-4 w-4" />
            Konzept hinzufügen
          </Button>

          {isCreatingConnection ? (
            <Button
              variant="outline"
              size="sm"
              onClick={cancelConnection}
              className="gap-1 text-red-500"
            >
              Verbindung abbrechen
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsCreatingConnection(true)}
              className="gap-1"
              disabled={isCreatingConnection}
            >
              <Link2 className="h-4 w-4" />
              Verbindung erstellen
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={generateNewConcepts}
            disabled={isGenerating || !currentSessionId}
            className="gap-1"
          >
            {isGenerating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generiere...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" />
                KI-Vorschläge
              </>
            )}
          </Button>
        </div>

        {/* Credit-Fehlermeldung mit Aufladebutton */}
        {creditsError && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive/30 rounded-md flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-start gap-3">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-destructive flex-shrink-0 mt-0.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <div>
                <h3 className="font-medium">Nicht genügend Credits</h3>
                <p className="text-sm text-muted-foreground">{creditsError.message}</p>
              </div>
            </div>
            <Button 
              onClick={() => window.location.href = "/payment"}
              className="whitespace-nowrap"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-2">
                <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
                <line x1="1" y1="10" x2="23" y2="10" />
              </svg>
              Credits aufladen
            </Button>
          </div>
        )}

        {showAddForm && (
          <div className="mb-6 flex gap-2 justify-center items-center">
            <input
              type="text"
              value={newConceptText}
              onChange={(e) => setNewConceptText(e.target.value)}
              placeholder="Neues Konzept eingeben..."
              className="px-3 py-1 border border-border rounded-md"
            />
            <Button size="sm" onClick={handleAddConcept}>Hinzufügen</Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowAddForm(false)}
            >
              Abbrechen
            </Button>
          </div>
        )}

        <Card className="border border-border/50 shadow-soft overflow-hidden animate-slide-up mb-8">
          <CardContent className="p-4">
            <div className="flex justify-end mb-2 gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setZoomLevel(prev => Math.max(0.5, prev - 0.1))}
                className="h-8 w-8 p-0"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              </Button>
              <div className="flex items-center text-xs">
                {Math.round(zoomLevel * 100)}%
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setZoomLevel(prev => Math.min(2, prev + 0.1))}
                className="h-8 w-8 p-0"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setZoomLevel(1);
                }}
                className="text-xs"
              >
                Reset
              </Button>
            </div>
            <div
              ref={mapContainerRef}
              className="w-full h-[900px] bg-white dark:bg-black/20 rounded-lg relative overflow-auto"
              onMouseMove={handleDrag}
              onMouseUp={endDrag}
              onMouseLeave={endDrag}
            >
              {(() => {
                const containerWidth = 1200;
                const containerHeight = 900;
                const centerX = containerWidth / 2;
                const centerY = containerHeight / 2;

                const padding = 100;
                const minX = Math.min(...concepts.map(c => c.x), 0) - padding;
                const maxX = Math.max(...concepts.map(c => c.x), containerWidth) + padding;
                const minY = Math.min(...concepts.map(c => c.y), 0) - padding;
                const maxY = Math.max(...concepts.map(c => c.y), containerHeight) + padding;

                const width = maxX - minX;
                const height = maxY - minY;

                const offsetX = centerX - (minX + width / 2);
                const offsetY = centerY - (minY + height / 2);

                return (
                  <div
                    className="absolute"
                    style={{
                      transform: `scale(${zoomLevel})`,
                      transformOrigin: 'center',
                      width: `${width}px`,
                      height: `${height}px`,
                      left: `50%`,
                      top: `50%`,
                      marginLeft: `${-width / 2 + offsetX}px`,
                      marginTop: `${-height / 2 + offsetY}px`,
                    }}
                  >
                    {connections.map(connection => {
                      const source = concepts.find(c => c.id === connection.sourceId);
                      const target = concepts.find(c => c.id === connection.targetId);
                      if (!source || !target) return null;

                      const x1 = source.x - minX;
                      const y1 = source.y - minY;
                      const x2 = target.x - minX;
                      const y2 = target.y - minY;

                      const midX = (x1 + x2) / 2;
                      const midY = (y1 + y2) / 2;

                      const isMainConnection = source.isMainTopic || target.isMainTopic;

                      return (
                        <div key={connection.id} className="absolute inset-0 pointer-events-none">
                          <svg
                            style={{
                              position: 'absolute',
                              width: `${width}px`,
                              height: `${height}px`,
                              left: 0,
                              top: 0,
                            }}
                          >
                            <line
                              x1={x1}
                              y1={y1}
                              x2={x2}
                              y2={y2}
                              stroke={isMainConnection ? "#3b82f6" : "currentColor"}
                              strokeWidth={isMainConnection ? "3" : "2"}
                              strokeOpacity={isMainConnection ? "0.7" : "0.5"}
                              strokeDasharray={isCreatingConnection ? "5,5" : ""}
                            />
                            <polygon
                              points={`${x2},${y2} ${x2-10},${y2-5} ${x2-10},${y2+5}`}
                              transform={`rotate(${Math.atan2(y2-y1, x2-x1) * 180/Math.PI + 90}, ${x2}, ${y2})`}
                              fill={isMainConnection ? "#3b82f6" : "currentColor"}
                              fillOpacity={isMainConnection ? "0.7" : "0.5"}
                            />
                          </svg>

                          <div
                            className="absolute bg-background/80 px-2 py-0.5 text-xs rounded border border-border/50 whitespace-nowrap cursor-pointer pointer-events-auto"
                            style={{
                              top: midY,
                              left: midX,
                              transform: 'translate(-50%, -50%)'
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              openConnectionPopup(connection.id);
                            }}
                          >
                            <span>[...]</span>
                          </div>
                        </div>
                      );
                    })}

                    {isCreatingConnection && connectionStart && (
                      <svg
                        style={{
                          position: 'absolute',
                          width: `${width}px`,
                          height: `${height}px`,
                          left: 0,
                          top: 0,
                        }}
                      >
                        <line
                          x1={(concepts.find(c => c.id === connectionStart)?.x || 0) - minX}
                          y1={(concepts.find(c => c.id === connectionStart)?.y || 0) - minY}
                          x2={draggedConcept ? (concepts.find(c => c.id === draggedConcept)?.x || 0) - minX : 0}
                          y2={draggedConcept ? (concepts.find(c => c.id === draggedConcept)?.y || 0) - minY : 0}
                          stroke="currentColor"
                          strokeDasharray="5,5"
                          strokeWidth="2"
                          strokeOpacity="0.7"
                        />
                      </svg>
                    )}

                    {concepts.map(concept => (
                      <div
                        key={concept.id}
                        className={`absolute p-2 rounded-lg border-2 group transition-all shadow-sm ${
                          connectionStart === concept.id
                            ? 'bg-primary/10 border-primary'
                            : isCreatingConnection
                            ? 'hover:bg-secondary hover:border-primary/50 border-border/50 bg-background cursor-pointer'
                            : 'border-border/50 bg-background hover:shadow-md hover:border-primary/30 transition-shadow'
                        } ${concept.isMainTopic 
                            ? 'font-bold bg-primary/20 border-primary w-32 py-3' 
                            : 'w-28'}`}
                        style={{
                          top: concept.y - minY - (concept.isMainTopic ? 25 : 20),
                          left: concept.x - minX - (concept.isMainTopic ? 64 : 56),
                          cursor: isCreatingConnection ? 'pointer' : 'move',
                          zIndex: concept.isMainTopic ? 10 : 5,
                          userSelect: 'none',
                        }}
                        onMouseDown={(e) => {
                          if (!isCreatingConnection && e.button === 0) {
                            startDrag(concept.id, e);
                          }
                        }}
                        onClick={(e) => {
                          if (isCreatingConnection) {
                            startConnection(concept.id);
                          }
                        }}
                      >
                        <div className="flex flex-col items-center">
                          <div className={`text-center ${concept.isMainTopic ? 'text-sm' : 'text-xs'} font-medium`}>
                            {concept.text}
                          </div>

                          {/* Zeige den Add-Button nur für Nicht-Hauptthemen */}
                          {!concept.isMainTopic && (
                            <div className="mt-1 flex gap-1 items-center justify-center">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-6 w-6 p-0 bg-primary/10"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  generateChildSuggestions(concept.id);
                                }}
                                title="Kind-Topic hinzufügen"
                              >
                                <Plus className="h-3 w-3" />
                              </Button>
                            </div>
                          )}

                          <div className="mt-1 flex gap-1 opacity-0 group-hover:opacity-100">
                            {!isCreatingConnection && (
                              <>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-4 w-4"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    startConnection(concept.id);
                                  }}
                                >
                                  <Link2 className="h-3 w-3" />
                                </Button>
                                {!concept.isMainTopic && (
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    className="h-4 w-4 text-red-500"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      deleteConcept(concept.id);
                                    }}
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })()}

              {selectedConnection && (() => {
                const connection = connections.find(c => c.id === selectedConnection);
                if (!connection) return null;

                return (
                  <div
                    className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-background border border-border rounded-lg shadow-lg p-4 z-50 w-72"
                    onClick={e => e.stopPropagation()}
                  >
                    <div className="flex justify-between items-center mb-2">
                      <h3 className="text-sm font-semibold">Verbindungsdetails</h3>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6"
                        onClick={closeConnectionPopup}
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </Button>
                    </div>

                    {isEditingConnection === connection.id ? (
                      <div className="flex flex-col gap-2">
                        <input
                          type="text"
                          value={connectionLabel}
                          onChange={(e) => setConnectionLabel(e.target.value)}
                          className="px-2 py-1 border rounded text-sm w-full"
                          autoFocus
                        />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={saveConnectionLabel}>
                            Speichern
                          </Button>
                          <Button size="sm" variant="outline" onClick={cancelEditingLabel}>
                            Abbrechen
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col gap-2">
                        <p className="text-sm break-words">{connection.label || "Keine Beschreibung"}</p>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setIsEditingConnection(connection.id);
                              setConnectionLabel(connection.label);
                            }}
                          >
                            Bearbeiten
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => deleteConnection(connection.id)}
                          >
                            Löschen
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          </CardContent>
        </Card>

      </div>
    </section>
  );
};

export default ConceptMapper;
