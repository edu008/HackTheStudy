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
  const connectedToParent = existingConcepts.filter(c => 
    connections.some(conn => 
      (conn.sourceId === parentConcept.id && conn.targetId === c.id) || 
      (conn.targetId === parentConcept.id && conn.sourceId === c.id)
    )
  );
  
  const parentX = parentConcept.x;
  const parentY = parentConcept.y;
  
  const angleToCenter = Math.atan2(parentY - centerY, parentX - centerX);
  
  const MAX_DISTANCE = -400;
  const childCount = connectedToParent.length + 1;
  const angleStep = (2 * Math.PI) / Math.max(childCount, 1);
  const childIndex = connectedToParent.length;
  const angleOffset = angleToCenter + (childIndex * angleStep);
  
  let x = parentX + MAX_DISTANCE * Math.cos(angleOffset);
  let y = parentY + MAX_DISTANCE * Math.sin(angleOffset);
  
  const minDistanceX = 80;
  const minDistanceY = 60;
  
  for (let attempt = 0; attempt < 3; attempt++) {
    const isFree = existingConcepts.every(concept => {
      if (concept.id === parentConcept.id) return true;
      
      const dx = Math.abs(concept.x - x);
      const dy = Math.abs(concept.y - y);
      return dx >= minDistanceX || dy >= minDistanceY;
    });
    
    if (isFree) {
      break;
    }
    
    const newRadius = MAX_DISTANCE + (attempt + 1) * 20;
    x = parentX + newRadius * Math.cos(angleOffset);
    y = parentY + newRadius * Math.sin(angleOffset);
  }
  
  const cardWidth = 100;
  const cardHeight = 40;
  x = Math.max(cardWidth / 2, Math.min(containerWidth - cardWidth / 2, x));
  y = Math.max(cardHeight / 2, Math.min(containerHeight - cardHeight / 2, y));
  
  return { x, y };
};

// Funktion zur Generierung eindeutiger IDs mit UUID
const generateUniqueId = () => uuidv4();

const ConceptMapper = ({ sessionId }: { sessionId?: string }) => {
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

  useEffect(() => {
    if (sessionId) {
      fetchInitialConcepts(sessionId);
    }
  }, [sessionId]);

  const fetchInitialConcepts = async (sessionId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/v1/results/${sessionId}`);
      const data = await response.json();
      console.log("API Response:", data);
      if (data.success && data.data?.analysis?.main_topic && data.data?.analysis?.subtopics) {
        const containerWidth = 700;
        const containerHeight = 500;
        const centerX = containerWidth / 2;
        const centerY = containerHeight / 2;
        const initialConcepts: Concept[] = [];

        initialConcepts.push({
          id: "main",
          text: data.data.analysis.main_topic,
          x: centerX,
          y: centerY,
          isMainTopic: true,
        });

        const initialConnections: Connection[] = [];
        const subtopicCount = data.data.analysis.subtopics.length;
        const radius = 250;
        
        data.data.analysis.subtopics.forEach((topic: string, index: number) => {
          const angle = (index * 2 * Math.PI) / subtopicCount;
          const x = centerX + radius * Math.cos(angle);
          const y = centerY + radius * Math.sin(angle);
          const newId = `${index + 1}`;
          
          initialConcepts.push({
            id: newId,
            text: topic,
            x,
            y,
          });
          
          initialConnections.push({
            id: generateUniqueId(),
            sourceId: "main",
            targetId: newId,
            label: ""
          });
        });

        setConcepts(initialConcepts);
        setConnections(initialConnections);

        toast({
          title: "Topics geladen",
          description: "Die Konzeptkarte wurde mit den analysierten Themen initialisiert.",
        });
      } else {
        throw new Error("Keine Topics gefunden");
      }
    } catch (error) {
      console.error("Fehler beim Laden der Topics:", error);
      toast({
        title: "Fehler",
        description: "Topics konnten nicht geladen werden.",
        variant: "destructive",
      });
    }
  };

  const generateConnectionsWithAI = async (existingConcepts: Concept[], sessionId: string) => {
    if (!sessionId) return;
  
    try {
      const response = await fetch(`${API_URL}/api/v1/generate-related-topics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await response.json();
  
      if (!data.success) throw new Error(data.error || "Generierung fehlgeschlagen");
  
      const containerWidth = 700;
      const containerHeight = 500;
      const centerX = containerWidth / 2;
      const centerY = containerHeight / 2;
  
      const allConcepts = [...existingConcepts];
      const newConcepts: Concept[] = [];
      const newConnections: Connection[] = [];
  
      const mainTopic = existingConcepts.find(c => c.isMainTopic);
      if (!mainTopic) throw new Error("Main Topic nicht gefunden");
  
      const subtopics = existingConcepts.filter(c =>
        connections.some(conn =>
          (conn.sourceId === mainTopic.id && conn.targetId === c.id) ||
          (conn.targetId === mainTopic.id && conn.sourceId === c.id)
        )
      );
  
      data.data.new_topics.forEach((topicText: string, index: number) => {
        const parentConcept = subtopics[index];
        if (parentConcept) {
          const position = calculatePositionRelativeToParent(
            parentConcept,
            [...allConcepts, ...newConcepts],
            containerWidth,
            containerHeight,
            centerX,
            centerY,
            connections
          );
          const newId = `${allConcepts.length + newConcepts.length + 1}`;
          newConcepts.push({
            id: newId,
            text: topicText,
            x: position.x,
            y: position.y,
          });

          const connection = data.data.new_connections.find(
            (conn: { source_text: string, target_text: string }) =>
              (conn.source_text === parentConcept.text && conn.target_text === topicText) ||
              (conn.target_text === parentConcept.text && conn.source_text === topicText)
          );

          newConnections.push({
            id: generateUniqueId(),
            sourceId: parentConcept.id,
            targetId: newId,
            label: connection ? connection.label : "Beziehung"
          });
        }
      });
  
      const mainTopicConnected = newConnections.some(conn => 
        conn.sourceId === mainTopic.id || conn.targetId === mainTopic.id
      );
      if (!mainTopicConnected && newConcepts.length > 0) {
        const connection = data.data.new_connections.find(
          (conn: { source_text: string, target_text: string }) =>
            conn.source_text === mainTopic.text || conn.target_text === mainTopic.text
        );
        newConnections.push({
          id: generateUniqueId(),
          sourceId: mainTopic.id,
          targetId: newConcepts[0].id,
          label: connection ? connection.label : "umfasst"
        });
      }
  
      setConcepts([...allConcepts, ...newConcepts]);
      setConnections((prev) => [...prev, ...newConnections]);
  
      toast({
        title: "KI-Vorschläge generiert",
        description: "Neue Kind-Subtopics wurden hinzugefügt.",
      });
    } catch (error) {
      console.error("Fehler beim Generieren der Verbindungen:", error);
      toast({
        title: "Fehler",
        description: "Kind-Subtopics konnten nicht generiert werden.",
        variant: "destructive",
      });
    }
  };

  const handleAddConcept = () => {
    if (!newConceptText.trim()) return;

    const containerWidth = 700;
    const containerHeight = 500;
    const centerX = containerWidth / 2;
    const centerY = containerHeight / 2;
    const newId = `${concepts.length + 1}`;
    
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
    if (!sessionId) {
      toast({
        title: "Fehler",
        description: "Keine Sitzung vorhanden. Bitte lade zuerst eine Datei hoch.",
        variant: "destructive",
      });
      return;
    }

    await generateConnectionsWithAI(concepts, sessionId);
  };

  const openConnectionPopup = (connectionId: string) => {
    setSelectedConnection(connectionId);
  };

  const closeConnectionPopup = () => {
    setSelectedConnection(null);
    setIsEditingConnection(null);
    setConnectionLabel("");
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
            disabled={isGenerating || !sessionId}
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
              className="w-full h-[500px] bg-white dark:bg-black/20 rounded-lg relative overflow-auto"
              onMouseMove={handleDrag}
              onMouseUp={endDrag}
              onMouseLeave={endDrag}
            >
              {(() => {
                const containerWidth = 700;
                const containerHeight = 500;
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
                        onClick={() => isCreatingConnection && startConnection(concept.id)}
                      >
                        <div className="flex flex-col items-center">
                          <div className={`text-center ${concept.isMainTopic ? 'text-sm' : 'text-xs'} font-medium`}>
                            {concept.text}
                          </div>

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

        <div className="text-center">
          <p className="text-muted-foreground mb-4">
            Ziehe Konzepte an verschiedene Positionen und erstelle Verbindungen mit Beschreibungen zwischen ihnen.
          </p>
          <Button
            variant="outline"
            onClick={() => {
              toast({
                title: "Konzeptkarte gespeichert",
                description: "Deine Konzeptkarte wurde gespeichert.",
              });
            }}
          >
            <ScanSearch className="h-4 w-4 mr-2" />
            Speichern und analysieren
          </Button>
        </div>
      </div>
    </section>
  );
};

export default ConceptMapper;
