import { useState, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, ScanSearch, Plus, Trash2, Link2, RefreshCw } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import { Topic } from '@/types';

interface Concept {
  id: string;
  text: string;
  x: number;
  y: number;
}

interface Connection {
  id: string;
  sourceId: string;
  targetId: string;
  label: string;
}

interface ConceptMapperProps {
  mainTopic?: { id: string; name: string };
  subtopics?: Topic[];
  connections?: {
    id: string;
    source_id: string;
    target_id: string;
    label: string;
  }[];
}

// Hilfsfunktion zur Konvertierung von Topics zu Concepts
const topicsToConcepts = (mainTopic: { id: string; name: string } | undefined, subtopics: Topic[] | undefined): Concept[] => {
  const concepts: Concept[] = [];
  
  // Zufällige Position für das Hauptthema in der Mitte
  if (mainTopic) {
    concepts.push({
      id: mainTopic.id,
      text: mainTopic.name,
      x: 200,
      y: 100
    });
  }
  
  // Positioniere Unterthemen im Kreis um das Hauptthema
  if (subtopics && subtopics.length > 0) {
    const radius = 150;
    const angleStep = (2 * Math.PI) / subtopics.length;
    
    subtopics.forEach((topic, index) => {
      const angle = index * angleStep;
      concepts.push({
        id: topic.id,
        text: topic.name,
        x: 200 + radius * Math.cos(angle),
        y: 100 + radius * Math.sin(angle)
      });
    });
  }
  
  return concepts;
};

// Hilfsfunktion zur Konvertierung von Connections
const convertConnections = (connections: { id: string; source_id: string; target_id: string; label: string; }[] | undefined): Connection[] => {
  if (!connections) return [];
  
  return connections.map(conn => ({
    id: conn.id,
    sourceId: conn.source_id,
    targetId: conn.target_id,
    label: conn.label
  }));
};

const sampleConcepts: Concept[] = [
  { id: '1', text: 'Sortieralgorithmen', x: 150, y: 100 },
  { id: '2', text: 'Quick Sort', x: 50, y: 200 },
  { id: '3', text: 'Merge Sort', x: 150, y: 250 },
  { id: '4', text: 'Bubble Sort', x: 250, y: 200 },
  { id: '5', text: 'Zeitkomplexität', x: 350, y: 150 },
];

const sampleConnections: Connection[] = [
  { id: 'c1', sourceId: '1', targetId: '2', label: 'Beispiel' },
  { id: 'c2', sourceId: '1', targetId: '3', label: 'Beispiel' },
  { id: 'c3', sourceId: '1', targetId: '4', label: 'Beispiel' },
  { id: 'c4', sourceId: '2', targetId: '5', label: 'O(n log n)' },
  { id: 'c5', sourceId: '3', targetId: '5', label: 'O(n log n)' },
  { id: 'c6', sourceId: '4', targetId: '5', label: 'O(n²)' },
];

const ConceptMapper: React.FC<ConceptMapperProps> = ({ mainTopic, subtopics, connections: initialConnections }) => {
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
  
  // Initialisiere Concepts und Connections basierend auf den Props
  useEffect(() => {
    // Wenn Props vorhanden sind, verwende sie, sonst Beispieldaten
    const initialConcepts = (mainTopic || subtopics) 
      ? topicsToConcepts(mainTopic, subtopics) 
      : sampleConcepts;
      
    const convertedConnections = initialConnections 
      ? convertConnections(initialConnections) 
      : sampleConnections;
    
    setConcepts(initialConcepts);
    setConnections(convertedConnections);
  }, [mainTopic, subtopics, initialConnections]);

  const handleAddConcept = () => {
    if (!newConceptText.trim()) return;
    
    const newId = (concepts.length + 1).toString();
    const newX = Math.random() * 300 + 50;
    const newY = Math.random() * 200 + 50;
    
    setConcepts([...concepts, {
      id: newId,
      text: newConceptText,
      x: newX,
      y: newY
    }]);
    
    setNewConceptText("");
    setShowAddForm(false);
    
    toast({
      title: "Konzept hinzugefügt",
      description: `"${newConceptText}" wurde zur Konzeptkarte hinzugefügt.`,
    });
  };

  const startDrag = (id: string, e: React.MouseEvent) => {
    const concept = concepts.find(c => c.id === id);
    if (!concept) return;
    
    setDraggedConcept(id);
    setDragOffset({
      x: e.clientX - concept.x,
      y: e.clientY - concept.y
    });
  };

  const handleDrag = (e: React.MouseEvent) => {
    if (!draggedConcept) return;
    
    setConcepts(concepts.map(c => {
      if (c.id === draggedConcept) {
        return {
          ...c,
          x: e.clientX - dragOffset.x,
          y: e.clientY - dragOffset.y
        };
      }
      return c;
    }));
  };

  const endDrag = () => {
    setDraggedConcept(null);
  };

  const startConnection = (id: string) => {
    if (isCreatingConnection) {
      if (id !== connectionStart) {
        // Complete the connection
        const newId = `c${connections.length + 1}`;
        setConnectionLabel("");
        setIsEditingConnection(newId);
        
        setConnections([...connections, {
          id: newId,
          sourceId: connectionStart!,
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
  };

  const saveConnectionLabel = () => {
    if (!isEditingConnection) return;
    
    setConnections(connections.map(conn => {
      if (conn.id === isEditingConnection) {
        return {
          ...conn,
          label: connectionLabel
        };
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

  const generateNewConcepts = () => {
    setIsGenerating(true);
    
    // Simulate AI generating new concepts
    setTimeout(() => {
      const newConcepts = [
        ...concepts,
        { id: '6', text: 'Heap Sort', x: 50, y: 300 },
        { id: '7', text: 'Stabilität', x: 300, y: 300 }
      ];
      
      const newConnections = [
        ...connections,
        { id: 'c7', sourceId: '1', targetId: '6', label: 'Beispiel' },
        { id: 'c8', sourceId: '6', targetId: '5', label: 'O(n log n)' },
        { id: 'c9', sourceId: '3', targetId: '7', label: 'stabil' },
        { id: 'c10', sourceId: '4', targetId: '7', label: 'stabil' },
        { id: 'c11', sourceId: '2', targetId: '7', label: 'nicht stabil' }
      ];
      
      setConcepts(newConcepts);
      setConnections(newConnections);
      setIsGenerating(false);
      
      toast({
        title: "Konzeptkarte erweitert",
        description: "Neue Konzepte und Verbindungen wurden hinzugefügt.",
      });
    }, 2000);
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
            disabled={isGenerating}
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
            <div 
              className="w-full h-[500px] bg-white dark:bg-black/20 rounded-lg relative overflow-hidden"
              onMouseMove={handleDrag}
              onMouseUp={endDrag}
              onMouseLeave={endDrag}
            >
              {/* Render connections */}
              {connections.map(connection => {
                const source = concepts.find(c => c.id === connection.sourceId);
                const target = concepts.find(c => c.id === connection.targetId);
                if (!source || !target) return null;
                
                // Calculate connection line coordinates
                const x1 = source.x;
                const y1 = source.y;
                const x2 = target.x;
                const y2 = target.y;
                
                // Calculate midpoint for label
                const midX = (x1 + x2) / 2;
                const midY = (y1 + y2) / 2;
                
                return (
                  <div key={connection.id} className="absolute inset-0 pointer-events-none">
                    <svg className="absolute inset-0 w-full h-full">
                      <line 
                        x1={x1} 
                        y1={y1} 
                        x2={x2} 
                        y2={y2} 
                        stroke="currentColor" 
                        strokeWidth="2"
                        strokeOpacity="0.5"
                        strokeDasharray={isCreatingConnection ? "5,5" : ""}
                      />
                      {/* Arrow marker at end of line */}
                      <polygon 
                        points={`${x2},${y2} ${x2-10},${y2-5} ${x2-10},${y2+5}`}
                        transform={`rotate(${Math.atan2(y2-y1, x2-x1) * 180/Math.PI + 90}, ${x2}, ${y2})`}
                        fill="currentColor"
                        fillOpacity="0.5"
                      />
                    </svg>
                    
                    {/* Connection label */}
                    <div 
                      className="absolute bg-background/80 px-2 py-0.5 text-xs rounded border border-border/50 whitespace-nowrap"
                      style={{
                        top: midY,
                        left: midX,
                        transform: 'translate(-50%, -50%)'
                      }}
                    >
                      {isEditingConnection === connection.id ? (
                        <div className="flex gap-1 pointer-events-auto">
                          <input
                            type="text"
                            value={connectionLabel}
                            onChange={(e) => setConnectionLabel(e.target.value)}
                            className="px-1 py-0.5 w-24 text-xs border rounded"
                            autoFocus
                          />
                          <Button 
                            size="icon" 
                            variant="ghost" 
                            className="h-5 w-5" 
                            onClick={saveConnectionLabel}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          </Button>
                          <Button 
                            size="icon" 
                            variant="ghost" 
                            className="h-5 w-5" 
                            onClick={cancelEditingLabel}
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </Button>
                        </div>
                      ) : (
                        <div className="flex gap-1 items-center">
                          <span>{connection.label}</span>
                          <div className="flex gap-0.5 ml-1 opacity-0 group-hover:opacity-100 pointer-events-auto">
                            <Button 
                              size="icon" 
                              variant="ghost" 
                              className="h-4 w-4" 
                              onClick={() => {
                                setIsEditingConnection(connection.id);
                                setConnectionLabel(connection.label);
                              }}
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-2 w-2">
                                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
                              </svg>
                            </Button>
                            <Button 
                              size="icon" 
                              variant="ghost" 
                              className="h-4 w-4 text-red-500" 
                              onClick={() => deleteConnection(connection.id)}
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-2 w-2">
                                <line x1="18" y1="6" x2="6" y2="18" />
                                <line x1="6" y1="6" x2="18" y2="18" />
                              </svg>
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              
              {/* Render current connection being created */}
              {isCreatingConnection && connectionStart && (
                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                  <line
                    x1={concepts.find(c => c.id === connectionStart)?.x || 0}
                    y1={concepts.find(c => c.id === connectionStart)?.y || 0}
                    x2={draggedConcept ? concepts.find(c => c.id === draggedConcept)?.x || 0 : 0}
                    y2={draggedConcept ? concepts.find(c => c.id === draggedConcept)?.y || 0 : 0}
                    stroke="currentColor"
                    strokeDasharray="5,5"
                    strokeWidth="2"
                    strokeOpacity="0.7"
                  />
                </svg>
              )}
              
              {/* Render concept nodes */}
              {concepts.map(concept => (
                <div
                  key={concept.id}
                  className={`absolute p-2 w-32 rounded-lg border group transition-all ${
                    connectionStart === concept.id
                      ? 'bg-primary/10 border-primary'
                      : isCreatingConnection
                      ? 'hover:bg-secondary hover:border-primary/50 border-border/50 bg-background cursor-pointer'
                      : 'border-border/50 bg-background hover:shadow-md hover:border-primary/30 transition-shadow'
                  }`}
                  style={{
                    top: concept.y - 25,
                    left: concept.x - 50,
                    cursor: isCreatingConnection ? 'pointer' : 'move'
                  }}
                  onMouseDown={(e) => !isCreatingConnection && startDrag(concept.id, e)}
                  onClick={() => isCreatingConnection && startConnection(concept.id)}
                >
                  <div className="flex flex-col items-center">
                    <div className="text-sm font-medium text-center">
                      {concept.text}
                    </div>
                    
                    <div className="mt-1 flex gap-1 opacity-0 group-hover:opacity-100">
                      {!isCreatingConnection && (
                        <>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-5 w-5"
                            onClick={(e) => {
                              e.stopPropagation();
                              startConnection(concept.id);
                            }}
                          >
                            <Link2 className="h-3 w-3" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-5 w-5 text-red-500"
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteConcept(concept.id);
                            }}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
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
