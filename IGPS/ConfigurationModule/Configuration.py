'''
Created on 24-03-2013

@author: Olek
'''

class Configuration():
    #TODO: Cleanup configuration
    minNumberToStartMatrixCreation = 3
    
    subMatrixSize = 1001  # assumed that single cell is 1 x 1 meter
    matrixSize    = 1101 # assumed that single cell is 1 x 1 meter
    
    # TODO: Remove fake mechanism
    fakePositionMin = 20
    fakePositionMax = 60
    
    #TODO: Turn off fake mechanism
    useFakeCalculationModule = True
    fakeSize = 5 # When greater then 13 issue appears
    
    nodesIdToBeCreated = [2, 3, 6]
    
if __name__ == "__main__":
    pass